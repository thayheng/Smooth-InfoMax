from arg_parser import arg_parser
from data import get_dataloader
from options_classify_syllables import get_options
from decoder.decoder_architectures import *
from utils.helper_functions import *
from utils import utils

device = 'cuda' if torch.cuda.is_available() else 'cpu'


def setup(OPTIONS, subset_size):

    CPC_MODEL_PATH = OPTIONS["cpc_model_path"]

    ENCODER = GIM_Encoder(OPTIONS, path=CPC_MODEL_PATH)
    ENCODER.encoder.eval()

    train_loader, _, test_loader, _ = get_dataloader.get_dataloader(
        OPTIONS, dataset="de_boer_sounds", split_and_pad=True, train_noise=False, shuffle=True, subset_size=subset_size)

    ####################################
    # TODO: THE DATASET USED FOR CLASSIFICATION IS NOT YET RESHUFFLED, SO STILL OLD TRAIN/TEST
    ####################################

    return ENCODER, train_loader, test_loader


def validation_loss(opt, encoder, classifier, test_loader, criterion):
    # based on GIM/ChatGPT
    total_step = len(test_loader)

    val_l = 0.0
    val_acc = 0.0
    starttime = time.time()

    for step, (gt_audio_batch, _, syllable_idx, _) in enumerate(test_loader):

        loss, accuracy = forward_and_loss(opt,
                                          encoder, classifier, gt_audio_batch, syllable_idx, criterion, detach=True)
        val_l += loss.item() / total_step
        val_acc += accuracy / total_step

    print(
        f"Validation Loss: Time (s): {time.time() - starttime:.1f} --- L: {val_l:.4f}, A: {val_acc:.2f}")

    # validation_l = np.mean(loss_epoch)
    return val_l, val_acc


def forward_and_loss(opt, encoder, classifier, gt_audio_batch, syllable_idx, criterion, detach):
    # (batch_size, 1, 10240)
    gt_audio_batch = gt_audio_batch.to(device)

    cs = encoder(gt_audio_batch)
    which_module = opt["which_module"]
    if which_module == "last":
        c = cs[-1].to(device)
    else:
        c = cs[int(which_module)-1].to(device)

    # (batch_size, l, c)
    c = c.permute(0, 2, 1)  # (b, c, l)
    temp2 = c.shape

    if opt["pooling"] == "max":
        pooled_c = nn.functional.adaptive_max_pool1d(c, 1)  # (b, c, 1)
        pooled_c = pooled_c.reshape(-1, 32)
    elif opt["pooling"] == "not":

        # pooled_c = nn.functional.adaptive_max_pool1d(torch.abs(c) , 1)  # (b, c, 1)
        # temp = pooled_c.shape
        # pooled_c = pooled_c.permute(0, 2, 1).reshape(-1, 32)  # (b, 1, c) -> (b, c)
        
        
        pooled_c = c.reshape(-1, temp2[1]*temp2[2])

    temp = pooled_c.shape

    if detach:
        classifier.eval()
        with torch.no_grad():
            outputs = classifier(pooled_c)
        classifier.train()
    else:
        outputs = classifier(pooled_c)

    n_classes = 9 if opt["labels"] == "syllables" else 3
    # transform syllable_idx to one-hot encoding
    targets = torch.nn.functional.one_hot(
        syllable_idx, num_classes=n_classes).to(device)
    loss = criterion(outputs, targets)

    accuracy, = utils.accuracy(outputs.data, syllable_idx.to(device))

    return loss, accuracy


def train(opt, encoder, classifier, logs, train_loader, test_loader, learning_rate, criterion):
    total_step = len(train_loader)

    epoch_printer = EpochPrinter(opt, train_loader, learning_rate, criterion)
    log_handler = LogHandler(opt, logs, train_loader,
                             criterion, encoder, learning_rate)

    classifier.to(device)
    classifier.train()

    optimizer = torch.optim.Adam(classifier.parameters(
    ), lr=learning_rate, weight_decay=1e-5)  # 1.5 * 10^-2 = 1.5/100

    training_losses = []
    validation_losses = []

    training_accuracies = []
    validation_accuracies = []

    for epoch in range(opt.encoder_config.start_epoch, opt["num_epochs"] + opt.encoder_config.start_epoch):
        training_l = 0.0
        training_acc = 0.0
        for step, (gt_audio_batch, _, syllable_idx, _) in enumerate(train_loader):
            epoch_printer(step, epoch)

            loss, accuracy = forward_and_loss(opt,
                encoder, classifier, gt_audio_batch, syllable_idx, criterion, detach=False)

            # zero the gradients
            optimizer.zero_grad()

            # backward pass and optimization step
            loss.backward()
            optimizer.step()

            training_l += loss.item() / total_step
            training_acc += accuracy / total_step
            # </> end for step

        validation_l, val_acc = validation_loss(opt,
                                                encoder, classifier, test_loader, criterion)

        training_losses.append(training_l)
        validation_losses.append(validation_l)

        training_accuracies.append(training_acc)
        validation_accuracies.append(val_acc)

        log_handler(classifier, epoch, optimizer,
                    training_losses, validation_losses, training_accuracies, validation_accuracies)

    # </> end epoch

    return classifier


def run_configuration(options, experiment_name):
    subset_size = options['subset']

    labels = options['labels']
    assert labels == "syllables" or labels == "vowels", "labels must be 'syllables' or 'vowels'"
    if labels == "syllables":
        n_classes = 9
    else:
        n_classes = 3
     

    if subset_size != "all":  # overwrite batch size to 9 content of subset
        options['batch_size'] = min(n_classes * int(subset_size), 32 * n_classes)  # 9 classes, but not enough data in validation set if 128 subset

    encoder, train_loader, test_loader = setup(options, subset_size)

    # create linear classifier
    LATENT_DIM = 32
    if options['pooling'] == "max":
        n_features = LATENT_DIM  # TODO: I added * 11 because max pooling is gone
    elif options['pooling'] == "not":
        n_features = (LATENT_DIM * 11) if options['which_module'] == "2" else (LATENT_DIM * 44)  # TODO: I added * 11 because max pooling is gone
    else:
        raise ValueError("pooling must be 'max' or 'not'")

    include_bias = options['include_bias_term']
    classifier = torch.nn.Sequential(torch.nn.Linear(n_features, n_classes, bias=include_bias))
    criterion = CrossEntropyLoss()
    lr = options['learning_rate']
    module = options['which_module']

    torch.cuda.empty_cache()

    options['experiment'] = experiment_name
    options['save_dir'] = f'{experiment_name}_experiment'
    options['log_path'] = f"{options['root_logs']}/CLASSIFIER_module_{module}/{experiment_name}"
    options['log_path_latent'] = options['log_path'] + "/latent_space"

    arg_parser.create_log_path(options)

    create_log_dir(opt.log_path)

    logs = logger.Logger(options)

    classifier = train(options, encoder, classifier, logs,
                       train_loader, test_loader, lr, criterion)

    torch.cuda.empty_cache()


class CrossEntropyLoss(nn.Module):
    def __init__(self):
        super().__init__()
        self.name = "CrossEntrop Loss"
        self.cross_entropy_loss = nn.CrossEntropyLoss()

    def forward(self, batch_inputs, batch_targets):
        assert batch_inputs.shape == batch_targets.shape
        # fix: RuntimeError: Expected floating point type for target with class probabilities, got Long
        batch_targets = batch_targets.float()

        return self.cross_entropy_loss(batch_inputs, batch_targets)


if __name__ == "__main__":

    OPTIONS = get_options()
    # random seeds
    torch.manual_seed(0)
    torch.cuda.manual_seed(0)
    np.random.seed(0)

    run_configuration(OPTIONS, "linear_model")
