"""
The aim here it to teach a perceptron where the 'cold' game positions are
in Wythoff's game

This is a 'gridworld' game where opponents take turns moving a tile,
each trying to reach the origin first. There's an optimal
way to play. In this there are 'cold' spots you want to force your
opponent into. Turns out there are arranged on the on set of diagonals.

More background at: 
https://en.wikipedia.org/wiki/Wythoff%27s_game
https://www.google.com/url?sa=t&rct=j&q=&esrc=s&source=web&cd=2&cad=rja&uact=8&ved=0ahUKEwjazcqI1MzbAhWpFzQIHYKiBe4QtwIIPDAB&url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3DAYOB-6wyK_I&usg=AOvVaw2sBye4bqZ368La03eC-jHF

The aim of the model below it to take an exact map of the exact cold spots, 
and teach an ANN where they are. It should be easy! 

...For some reason, my model does not learn at all!

After many permutations, I think it has to do with how I'm constructing the 
input (see line 151) but it could be anything. Eyes open.

I've construted a minimal-ish example balow but I've been trying to figure this 
out for too long and need some new eyes.

Help. :)
"""

import os, csv
import sys

import errno

import torch
import torch.optim as optim
import torch.nn.functional as F
from torch.autograd import Variable
from tensorboardX import SummaryWriter

import numpy as np
import matplotlib.pyplot as plt
from scipy.constants import golden

import skimage
from skimage import data, io

import gym
from gym import wrappers
import azad.local_gym

from azad.models import OneLinQN
from azad.models import HotCold
from azad.policy import epsilon_greedy
from azad.policy import greedy
from azad.util import ReplayMemory

from azad.exp.wythoff import *


class HotCold(nn.Module):
    """Layers for learning Wythoff optimal play
    
    As described in:
    
    Muyesser, N.A., Dunovan, K. & Verstynen, T., 2018. Learning model-based 
    strategies in simple environments with hierarchical q-networks. , pp.1–29. A
    vailable at: http://arxiv.org/abs/1801.06689.
    """

    def __init__(self, in_channels=2):
        super(HotCold, self).__init__()
        self.fc1 = nn.Linear(in_channels, 15)
        self.fc2 = nn.Linear(15, 1)

    def forward(self, x):
        x = F.sigmoid(self.fc1(x))
        return F.sigmoid(self.fc2(x))


def testing_strategist(path,
                       num_trials=1000,
                       learning_rate=0.01,
                       strategic_default_value=0.5,
                       wythoff_name_stumbler='Wythoff50x50',
                       wythoff_name_strategist='Wythoff50x50',
                       log=False,
                       seed=None):
    """A minimal example."""

    # -------------------------------------------
    # Setup
    # -------------------------------------------
    # Create path
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise

    env = gym.make('{}-v0'.format(wythoff_name_strategist))
    env = wrappers.Monitor(
        env, './tmp/{}-v0-1'.format(wythoff_name_strategist), force=True)

    possible_actions = [(-1, 0), (0, -1), (-1, -1)]

    # Train params
    batch_size = 12

    # -------------------------------------------
    # Log setup
    if log:
        writer = SummaryWriter(log_dir=path)

    # -------------------------------------------
    # Seeding...
    env.seed(seed)
    np.random.seed(seed)

    # -------------------------------------------
    # Build a Strategist, its memory, and its optimizer

    # How big are the boards?
    m, n, board = peak(wythoff_name_strategist)
    o, p, _ = peak(wythoff_name_stumbler)

    # Create a model, of the right size.
    model = HotCold(2)
    optimizer = optim.SGD(model.parameters(), lr=learning_rate)
    memory = ReplayMemory(10000)

    # Run learning trials. The 'stumbler' is just the opt
    # cold board
    for trial in range(num_trials):
        # The cold spots are '1' everythig else is '0'
        strategic_value = create_cold_board(o, p)

        # ...Into tuples
        s_data = convert_ijv(strategic_value)
        for d in s_data:
            memory.push(*d)

        # Sample data....
        # (this is a necessary holdover from the real implementation).
        coords = []
        values = []
        samples = memory.sample(batch_size)

        for c, v in samples:
            coords.append(c)
            values.append(v)

        coords = torch.tensor(
            np.vstack(coords), requires_grad=True, dtype=torch.float)
        values = torch.tensor(values, requires_grad=True, dtype=torch.float)

        # Scale coords
        coords = coords / m

        # Making some preditions,
        predicted_values = model(coords).detach().squeeze()

        # and find their loss.
        # (choose any doesn't matter)
        # loss = F.smooth_l1_loss(values, predicted_values)
        # loss = F.mse_loss(values, predicted_values)
        # loss = F.mse_loss(
        #     torch.clamp(values, 0, 1), torch.clamp(predicted_values, 0, 1))
        loss = F.binary_cross_entropy(values, predicted_values)

        # Walk down the hill of righteousness!
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        # Compare strategist and stumbler. Count strategist wins.
        # win = evaluate_models(stumbler_model, model, stumbler_env, env)

        # Use the trained strategist to generate a bias_board,
        bias_board = estimate_strategic_value(m, n, model)

        if log:
            writer.add_scalar(os.path.join(path, 'error'), loss.data[0], trial)

            plot_wythoff_board(
                strategic_value, path=path, name='strategy_board.png')
            writer.add_image(
                'Expected value board',
                skimage.io.imread(os.path.join(path, 'strategy_board.png')))

            plot_wythoff_board(bias_board, path=path, name='bias_board.png')
            writer.add_image(
                'Strategist learning',
                skimage.io.imread(os.path.join(path, 'bias_board.png')))

    # The end
    if log:
        writer.close()

    return model, env