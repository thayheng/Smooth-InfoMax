# %%
import time
import importlib
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


def encoder_lambda(xs_batch):
    # No auto differentaiton support error:
    # Chat gpt:
    # It looks like the issue is with the encode function being called with a gradient-enabled tensor as the audios argument, which is causing the stack function to be called with a gradient-enabled tensor as an argument. This is causing the RuntimeError because the stack function does not support automatic differentiation when one of its arguments requires a gradient.
    # One solution would be to disable gradients for the audios tensor before calling the encode function. You can do this by using the torch.no_grad context manager or the detach method. Here's what the modified code would look like using the torch.no_grad context manager:

    # Gim_encoder is outerscope variable
    with torch.no_grad():
        return encode(xs_batch, GIM_encoder, depth=3)


device = 'cuda' if torch.cuda.is_available() else 'cpu'
opt['batch_size'] = 8

GIM_encoder, _ = load_model(path='./g_drive_model/model_180.ckpt')
GIM_encoder.eval()

random.seed(0)


class LogHandler():
    def __init__(self, logs, train_loader) -> None:
        self.total_step = len(train_loader)
        self.logs = logs

    def call(self, loss_epoch) -> None:
        self.logs.append_train_loss([x / self.total_step for x in loss_epoch])


class EpochPrinter():
    def __init__(self, train_loader) -> None:
        self.starttime = time.time()

        self.print_idx = 100
        self.step = 0
        self.total_step = len(train_loader)

    def call(self, step, epoch) -> None:
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
    epoch_printer = EpochPrinter(train_loader)
    log_handler = LogHandler(logs, train_loader)

    decoder.to(device)
    decoder.train()

    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(decoder.parameters(), lr=1.5e-2)

    for epoch in range(5):
        loss_epoch = [0]
        
        for step, (org_audio, enc_audio, _, _, _) in enumerate(train_loader):
            epoch_printer(step, epoch)

            enc_audios = enc_audio.to(device)  # torch.Size([2, 1, 2047, 512])
            enc_audios = enc_audios.squeeze(dim=1)  # torch.Size([2, 2047, 512])
            enc_audios = enc_audios.permute(0, 2, 1)  # torch.Size([2, 512, 2047])

            org_audio = org_audio.to(device)  # torch.Size([2, 1, 10240])

            # zero the gradients
            optimizer.zero_grad()

            # forward pass
            outputs = decoder(enc_audios)
            outputs = outputs.squeeze(dim=1)

            org_audio = org_audio.squeeze(dim=1)  # torch.Size([2,10240])
            loss = criterion(outputs, org_audio)

            # backward pass and optimization step
            loss.backward()
            optimizer.step()

            # # print the loss at each step
            # epoch_loss += loss.item()  # sum of errors instead of mean

            loss_epoch[0] += loss.item()
            # </> end for step

        log_handler(loss_epoch) # store losses + models

    # torch.save(decoder.state_dict(), "decoder_layer_3.pth")
    # plt.plot(errors)  # plot the errors
    # plt.xlabel("Training steps")
    # plt.ylabel("Training error")
    # plt.show()

    return decoder

# %%


if __name__ == "__main__":
    arg_parser.create_log_path(opt)

    experiment_name = 'RMSE_decoder'
    opt['experiment'] = experiment_name,
    opt['save_dir'] = f'{experiment_name}_experiment',
    opt['log_path'] = f'./logs/{experiment_name}_experiment',
    opt['log_path_latent'] = f'./logs/{experiment_name}_experiment/latent_space',

    logs = logger.Logger(opt)

    # load the data
    train_loader, _, _, _ = get_dataloader.get_de_boer_sounds_decoder_data_loaders(
        opt,
        GIM_encoder=encoder_lambda)

    two_layer_decoder = TwoLayerDecoder()
    decoder = train(two_layer_decoder, logs, train_loader)

    logs.create_log(two_layer_decoder)

    # torch.cuda.empty_cache()


# %%
