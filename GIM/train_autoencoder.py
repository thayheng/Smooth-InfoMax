# %%
import time
import importlib
from typing import Any
import decoder_architectures
import helper_functions
import torch.nn as nn
from options import OPTIONS as opt
import torch
from utils import logger
from arg_parser import arg_parser
from data import get_dataloader
import matplotlib.pyplot as plt
import random


if(True):
    importlib.reload(decoder_architectures)
    importlib.reload(helper_functions)

    from decoder_architectures import *
    from helper_functions import *


def encode(audio, model, depth=1):
    audios = audio.unsqueeze(0)
    model_input = audios.to(device)

    for idx, layer in enumerate(model.module.fullmodel):
        context, z = layer.get_latents(model_input)
        model_input = z.permute(0, 2, 1)

        if(idx == depth - 1):
            return z





def load_model(path):
    print("loading model")
    # Code comes from: def load_model_and_optimizer()
    kernel_sizes = [10, 8, 4, 4, 4]
    strides = [5, 4, 2, 2, 2]
    padding = [2, 2, 2, 2, 1]
    enc_hidden = 512
    reg_hidden = 256

    calc_accuracy = False
    num_GPU = None

    # Initialize model.
    model = full_model.FullModel(
        opt,
        kernel_sizes=kernel_sizes,
        strides=strides,
        padding=padding,
        enc_hidden=enc_hidden,
        reg_hidden=reg_hidden,
        calc_accuracy=calc_accuracy,
    )

    # Run on only one GPU for supervised losses.
    if opt["loss"] == 2 or opt["loss"] == 1:
        num_GPU = 1

    model, num_GPU = model_utils.distribute_over_GPUs(
        opt, model, num_GPU=num_GPU)

    optimizer = torch.optim.Adam(model.parameters(), lr=opt['learning_rate'])
    model.load_state_dict(torch.load(path, 
        map_location=device
        ))

    return model, optimizer


device = 'cuda' if torch.cuda.is_available() else 'cpu'
opt['batch_size'] = 8

GIM_encoder, _ = load_model(path='./g_drive_model/model_180.ckpt')
GIM_encoder.eval()

random.seed(0)

def encoder_lambda(xs_batch):
    # Gim_encoder is outerscope variable
    with torch.no_grad():
        return encode(xs_batch, GIM_encoder, depth=1)





class LogHandler():
    def __init__(self, logs, train_loader) -> None:
        self.total_step = len(train_loader)
        self.logs: logger.Logger = logs

    def __call__(self,loss_epoch, *args: Any, **kwds: Any) -> Any:
        self.logs.append_train_loss([x / self.total_step for x in loss_epoch])


class EpochPrinter():
    def __init__(self, train_loader) -> None:
        self.starttime = time.time()

        self.print_idx = 100
        self.step = 0
        self.total_step = len(train_loader)

    def __call__(self, step, epoch, *args: Any, **kwds: Any) -> Any:
        if step % self.print_idx == 0:
            print(
                "Epoch [{}/{}], Step [{}/{}], Time (s): {:.1f}".format(
                    epoch + 1,
                    opt["num_epochs"] + opt["start_epoch"],
                    step,
                    self.total_step,
                    time.time() - self.starttime,
                )
            )


def train(decoder, logs, train_loader):
    # epoch_printer = EpochPrinter(train_loader)
    # log_handler = LogHandler(logs, train_loader)

    decoder.to(device)
    decoder.train()

    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(decoder.parameters(), lr=1.5e-2)

    for epoch in range(opt["start_epoch"], opt["num_epochs"] + opt["start_epoch"]):

        loss_epoch = [0]

        for step, (org_audio, enc_audio, _, _, _) in enumerate(train_loader):
            # epoch_printer(step, epoch)

            enc_audios = enc_audio.to(device)
            org_audio = org_audio.to(device)

            # zero the gradients
            optimizer.zero_grad()

            # forward pass
            outputs = decoder(enc_audios)
            loss = criterion(outputs, org_audio)

            # backward pass and optimization step
            loss.backward()
            optimizer.step()

            # print the loss at each step

            loss_epoch[0] += loss.item()
            # </> end for step

        # log_handler(loss_epoch) # store losses
    return decoder

# %%


if __name__ == "__main__":
    torch.cuda.empty_cache()




    arg_parser.create_log_path(opt)

    experiment_name = 'RMSE_decoder'
    opt['experiment'] = experiment_name
    opt['save_dir'] = f'{experiment_name}_experiment'
    opt['log_path'] = f'./logs/{experiment_name}_experiment'
    opt['log_path_latent'] = f'./logs/{experiment_name}_experiment/latent_space'
    opt['num_epochs'] = 5

    logs = logger.Logger(opt)

    # load the data
    train_loader, _, _, _ = get_dataloader.get_de_boer_sounds_decoder_data_loaders(
        opt,
        GIM_encoder=encoder_lambda)

    two_layer_decoder = OneLayerDecoder()
    decoder = train(two_layer_decoder, logs, train_loader)

    logs.create_log(two_layer_decoder)

    torch.cuda.empty_cache()


# %%
