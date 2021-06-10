import os
from tqdm import tqdm
import pickle
import argparse
import warnings
import time
import numpy as np
import torch
from torch.optim import SGD
from torch.nn import CrossEntropyLoss

from utils import set_seed, load_model, save, get_model, update_optimizer, get_data
from epoch import train_epoch, val_epoch, test_epoch
from cli import add_all_parsers
# TEMPORARY HACK #
warnings.filterwarnings("ignore")


def train(args):
    set_seed(args, use_gpu=torch.cuda.is_available())
    train_loader, val_loader, test_loader, dataset_attributes = get_data(args)

    model = get_model(args, n_classes=dataset_attributes['n_classes'])
    criteria = CrossEntropyLoss()

    if args.use_gpu:
        torch.cuda.set_device(0)
        model.cuda()
        criteria.cuda()

    optimizer = SGD(model.parameters(), lr=args.lr, momentum=0.9, weight_decay=args.mu, nesterov=True)

    # Containers for storing statistics over epochs
    loss_train, train_accuracy, topk_train_accuracy = [], [], []
    loss_val, val_accuracy, topk_val_accuracy, average_k_val_accuracy = [], [], [], []

    best_val_accuracy = np.float('-inf')
    save_name = args.save_name_xp.strip()
    save_dir = os.path.join(os.getcwd(), 'results', save_name)
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    print('args.k : ', args.k)

    lmbda_best_acc = None

    for epoch in tqdm(range(args.n_epochs), desc='epoch', position=0):
        t = time.time()
        optimizer = update_optimizer(optimizer, lr_schedule=dataset_attributes['lr_schedule'], epoch=epoch)

        loss_epoch_train, epoch_accuracy_train, epoch_top_k_accuracy_train = train_epoch(model, optimizer, train_loader,
                                                                                         criteria, loss_train,
                                                                                         train_accuracy,
                                                                                         topk_train_accuracy, args.k,
                                                                                         dataset_attributes['n_train'],
                                                                                         args.use_gpu)

        loss_epoch_val, epoch_accuracy_val, epoch_top_k_accuracy_val, \
            epoch_average_k_accuracy_val, lmbda_val = val_epoch(model, val_loader, criteria,
                                                                loss_val, val_accuracy,
                                                                topk_val_accuracy, average_k_val_accuracy,
                                                                args.k, dataset_attributes, args.use_gpu)

        # no matter what, save model at every epoch
        save(model, optimizer, epoch, os.path.join(save_dir, save_name + '_weights.tar'))

        # save model with best val accuracy
        if epoch_accuracy_val > best_val_accuracy:
            best_val_accuracy = epoch_accuracy_val
            lmbda_best_acc = lmbda_val
            save(model, optimizer, epoch, os.path.join(save_dir, save_name + '_weights_best_acc.tar'))

        print()
        print(f'epoch {epoch} took {time.time()-t:.2f}')
        print(f'loss_epoch_train : {loss_epoch_train}')
        print(f'loss_epoch_val : {loss_epoch_val}')
        print(f'train accuracy : {epoch_accuracy_train} / train top_k accuracy : {epoch_top_k_accuracy_train}')
        print(f'val accuracy : {epoch_accuracy_val} / val top_k accuracy : {epoch_top_k_accuracy_val} / '
              f'val average_k accuracy : {epoch_average_k_accuracy_val}')

    # load weights corresponding to best val accuracy and evaluate on test
    load_model(model, os.path.join(save_dir, save_name + '_weights_best_acc.tar'), args.use_gpu)
    loss_test_ba, accuracy_test_ba, \
        top_k_accuracy_test_ba, average_k_accuracy_test_ba = test_epoch(model, test_loader, criteria, args.k,
                                                                        lmbda_best_acc, args.use_gpu,
                                                                        dataset_attributes['n_test'])

    # Save the results as a dictionary and save it as a pickle file in desired location

    results = {'loss_train': loss_train, 'train_accuracy': train_accuracy, 'topk_train_accuracy': topk_train_accuracy,
               'loss_val': loss_val, 'val_accuracy': val_accuracy, 'topk_val_accuracy': topk_val_accuracy,
               'average_k_val_accuracy': average_k_val_accuracy,
               'test_results': {'loss': loss_test_ba,
                                'accuracy': accuracy_test_ba,
                                'topk-accuracy': top_k_accuracy_test_ba,
                                'averagek-accuracy': average_k_accuracy_test_ba},
               'params': args.__dict__}

    with open(os.path.join(save_dir, save_name + '.pkl'), 'wb') as f:
        pickle.dump(results, f)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    add_all_parsers(parser)
    args = parser.parse_args()
    train(args)
