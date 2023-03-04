import torch.nn as nn

from models import (
    cnn_encoder,
    loss_InfoNCE,
    autoregressor
)


class IndependentModule(nn.Module):
    def __init__(
        self, opt,
        enc_kernel_sizes, enc_strides, enc_padding, nb_channels_cnn, nb_channels_regress, enc_input=1, calc_accuracy=False,
    ):
        super(IndependentModule, self).__init__()

        self.opt = opt
        self.calc_accuracy = calc_accuracy
        self.nb_channels_cnn = nb_channels_cnn
        self.nb_channels_regressor = nb_channels_regress

        # encoder, out: B x L x C = (22, 55, 512)
        self.encoder = cnn_encoder.CNNEncoder(
            inp_nb_channels=enc_input,
            out_nb_channels=nb_channels_cnn,
            kernel_sizes=enc_kernel_sizes,
            strides=enc_strides,
            padding=enc_padding,
        )

        if self.opt["auto_regressor_after_module"]:
            self.autoregressor = autoregressor.Autoregressor(
                opt=opt, input_size=self.nb_channels_cnn, hidden_dim=self.nb_channels_regressor
            )

            # hidden dim of the autoregressor is the input dim of the loss
            self.loss = loss_InfoNCE.InfoNCE_Loss(
                opt, hidden_dim=self.nb_channels_regressor, enc_hidden=self.nb_channels_cnn, calc_accuracy=calc_accuracy)
        else:
            # hidden dim of the encoder is the input dim of the loss
            self.loss = loss_InfoNCE.InfoNCE_Loss(
                opt, hidden_dim=self.nb_channels_cnn, enc_hidden=self.nb_channels_cnn, calc_accuracy=calc_accuracy)

    def get_latents(self, x):
        """
        Calculate the latent representation of the input (using both the encoder and the autoregressive model)
        :param x: batch with sampled audios (dimensions: B x C x L)
        :return: c - latent representation of the input (either the output of the autoregressor,
                if use_autoregressor=True, or the output of the encoder otherwise)
                z - latent representation generated by the encoder (or x if self.use_encoder=False)
                both of dimensions: B x L x C
        """
        # encoder in and out: B x C x L, permute to be  B x L x C
        z = self.encoder(x)
        z = z.permute(0, 2, 1)

        if self.opt["auto_regressor_after_module"]:
            c = self.autoregressor(z)
            return c, z
        else:
            return z, z

    def forward(self, x):
        """
        combines all the operations necessary for calculating the loss and accuracy of the network given the input
        :param x: batch with sampled audios (dimensions: B x C x L)
        :return: total_loss - average loss over all samples, timesteps and prediction steps in the batch
                accuracies - average accuracies over all samples, timesteps and predictions steps in the batch
                c - latent representation of the input (either the output of the autoregressor,
                if use_autoregressor=True, or the output of the encoder otherwise)
        """

        # B x L x C = Batch size x #channels x length
        c, z = self.get_latents(x)  # B x L x C

        total_loss, accuracies = self.loss.get_loss(z, c)

        # for multi-GPU training
        total_loss = total_loss.unsqueeze(0)
        accuracies = accuracies.unsqueeze(0)

        return total_loss, accuracies, z
