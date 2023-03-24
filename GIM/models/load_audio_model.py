import torch

from models import full_model
from utils import model_utils


def load_model_and_optimizer(
    opt, lr, reload_model=False, calc_accuracy=False, num_GPU=None
):
    # Initialize model.
    model = full_model.FullModel(
        opt,
        calc_accuracy=calc_accuracy,
    )

    # Run on only one GPU for supervised losses.
    if opt["loss"] == 2 or opt["loss"] == 1:
        num_GPU = 1

    model, num_GPU = model_utils.distribute_over_GPUs(
        opt, model, num_GPU=num_GPU)

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    model, optimizer = model_utils.reload_weights(
        opt, model, optimizer, reload_model)

    model.train()
    print(model)

    return model, optimizer
