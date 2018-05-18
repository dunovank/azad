import os
import errno

import torch
import torch.optim as optim
import torch.nn.functional as F
from torch.autograd import Variable
from tensorboardX import SummaryWriter

import numpy as np
import matplotlib.pyplot as plt

import gym
from gym import wrappers
import azad.local_gym

from azad.stumblers import OneLinQN
from azad.policy import epsilon_greedy

# ---------------------------------------------------------------
# Handle dtypes for the device
USE_CUDA = torch.cuda.is_available()
FloatTensor = torch.cuda.FloatTensor if USE_CUDA else torch.FloatTensor
LongTensor = torch.cuda.LongTensor if USE_CUDA else torch.LongTensor
ByteTensor = torch.cuda.ByteTensor if USE_CUDA else torch.ByteTensor
Tensor = FloatTensor

# ---------------------------------------------------------------


def plot_wythoff_expected_values(m, n, model, path=None):
    # Build the matrix a values for each (i, j) board
    values = np.zeros((m, n))
    for i in range(m):
        for j in range(n):
            values[i, j] = np.max(model(Tensor([i, j])).detach().numpy())

    # !
    plt.matshow(values)

    # Save an image?
    if path is not None:
        plt.savefig(os.join.path(path, 'wythoff_expected_values.png'))

    # plt.show()
    plt.pause(0.01)
    plt.close()


def wythoff_1(path,
              num_trials=10,
              epsilon=0.1,
              gamma=0.8,
              learning_rate=0.1,
              wythoff_name='Wythoff3x3',
              log_path=None,
              plot_progress=False,
              seed=None):
    """Train a Q-agent to play Wythoff's game, using SGD."""

    # -------------------------------------------
    # Create path
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise

    # -------------------------------------------
    # Tensorboard setup    
    if log_path is None:
        log_path = path
    writer = SummaryWriter(log_dir=log_path)

    # -------------------------------------------
    # The world is a pebble on a board
    env = gym.make('{}-v0'.format(wythoff_name))
    env = wrappers.Monitor(
        env, './tmp/{}-v0-1'.format(wythoff_name), force=True)

    # -------------------------------------------
    # Seeding...
    env.seed(seed)
    np.random.seed(seed)

    # -------------------------------------------
    # Valid moves (in this simplified instantiation)
    possible_actions = [(-1, 0), (0, -1), (-1, -1)]

    # -------------------------------------------
    # Build a Q agent, its memory, and its optimizer

    # How big is the board?
    x, y, board = env.reset()
    env.close()
    m, n = board.shape

    # Create a model of the right size
    model = OneLinQN(m * n, len(possible_actions))
    optimizer = optim.SGD(model.parameters(), lr=learning_rate)

    # -------------------------------------------
    # Run some trials
    trials = []
    trial_steps = []
    trial_state_xs = []
    trial_state_ys = []
    trial_rewards = []
    trial_values = []
    trial_move_xs = []
    trial_move_ys = []
    errors = []

    for trial in range(num_trials):
        x, y, board = env.reset()
        board = Tensor(board.reshape(m * n))

        steps = 0
        while True:
            # -------------------------------------------
            # TODO
            # env.render()

            # -------------------------------------------
            # Look at the world and approximate its value.
            Qs = model(board).squeeze()

            # Make a decision.
            action_index = epsilon_greedy(Qs, epsilon)
            action = possible_actions[int(action_index)]

            Q = Qs[int(action_index)]

            (x, y, next_board), reward, done, _ = env.step(action)
            next_board = Tensor([next_board.reshape(m * n)])

            # Update move counter
            steps += 1

            # ---
            # Learn w/ SGD
            max_Q = model(next_board).detach().max()
            next_Q = reward + (gamma * max_Q)
            loss = F.smooth_l1_loss(Q, next_Q)

            optimizer.zero_grad()
            loss.backward(retain_graph=True)  # retain is needed for opp. WHY?
            optimizer.step()

            # Shuffle state notation
            board = next_board

            # -------------------------------------------
            # Save results
            trials.append(trial)
            trial_state_xs.append(int(x))
            trial_state_ys.append(int(y))
            trial_steps.append(int(steps))
            trial_rewards.append(float(reward))
            trial_move_xs.append(action[0])
            trial_move_ys.append(action[1])
            trial_values.append(float(Q))

            # -
            writer.add_scalar(os.path.join(log_path, 'Q'), Q, trial)
            writer.add_scalar(os.path.join(log_path, 'reward'), reward, trial)

            # -------------------------------------------
            # If the game is over, stop
            if done:
                break

            # -------------------------------------------
            # Otherwise the opponent moves
            action_index = np.random.randint(0, len(possible_actions))
            action = possible_actions[action_index]

            Q = Qs[int(action_index)].squeeze()

            (x, y, next_board), reward, done, info = env.step(action)
            next_board = Tensor([next_board.reshape(m * n)])

            # Flip signs so opp victories are punishments
            if reward > 0:
                reward *= -1

            # -
            writer.add_scalar(os.path.join(log_path, 'opp_Q'), Q, trial)
            writer.add_scalar(
                os.path.join(log_path, 'opp_reward'), reward, trial)

            # ---
            # Learn from your opponent
            max_Q = model(next_board).detach().max()
            next_Q = reward + (gamma * max_Q)
            loss = F.smooth_l1_loss(Q, next_Q)

            # optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            # Plot?
            if (trial % 10) == 0 and plot_progress:
                m, n = info["m"], info["n"]
                plot_wythoff_expected_values(m, n, model)

            if done:
                break

        # save min loss for this trial
        writer.add_scalar(os.path.join(log_path, 'error'), loss.data[0], trial)

    # Cleanup and end
    writer.close()

    results = list(
        zip(trials, trial_steps, trial_state_xs, trial_state_ys, trial_move_xs,
            trial_move_ys, trial_rewards, trial_values))
    return results