import logging
logging.getLogger('some_logger')
logging.basicConfig(filename="run_name.log", level=logging.INFO)

import os
import numpy as np
import random
import pickle
import torch.nn as nn
import torch.optim as optim
import torch

from sp_data.data_utils import SPbinaryData, BinarySPDataset, SPCSpredictionData, CSPredsDataset, collate_fn
from models.transformer_nmt import TransformerModel


def weighted_avg_results_for_dataset(test_results_for_ds):
    num_batches_per_ds = [td[0] for td in test_results_for_ds]
    weights = [nb / sum(num_batches_per_ds) for nb in num_batches_per_ds]
    negative_result = sum([weights[i] * test_results_for_ds[i][1] for i in range(len(weights))])
    positive_result = sum([weights[i] * test_results_for_ds[i][2] for i in range(len(weights))])
    return negative_result, positive_result


def get_pos_neg_for_datasets(test_datasets, model, data_folder, use_aa_len=200, epoch=0):
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    test_results_for_ds = []
    for test_ds in test_datasets:
        model.eval()
        dataset = BinarySPDataset(data_folder + test_ds, use_aa_len=use_aa_len)
        dataset_loader = torch.utils.data.DataLoader(dataset,
                                                     batch_size=64, shuffle=True,
                                                     num_workers=4)
        total_positives, total_negatives = 0, 0
        total_positive_hits, total_negative_hits = 0, 0
        for batch in dataset_loader:
            x, y = batch['emb'], batch['lbl']
            x, y = x.to(device, dtype=torch.float32), y.to(device).to(torch.float)
            if use_aa_len != 200:
                x = x[:, :use_aa_len, :]
            with torch.no_grad():
                model_preds = model(x.permute(0, 2, 1))
            positive_preds, negative_preds = model_preds >= 0.5, model_preds < 0.5
            positive_pred_inds, negative_pred_inds = torch.nonzero(positive_preds).reshape(-1).detach().cpu().numpy(), \
                                                     torch.nonzero(negative_preds).reshape(-1).detach().cpu().numpy()
            actual_positives, actual_negatives = y >= 0.5, y < 0.5
            actual_positives_inds, actual_negatives_inds = torch.nonzero(actual_positives).reshape(
                -1).detach().cpu().numpy(), \
                                                           torch.nonzero(actual_negatives).reshape(
                                                               -1).detach().cpu().numpy()
            positive_hits = len(set(positive_pred_inds).intersection(actual_positives_inds))
            negative_hits = len(set(negative_pred_inds).intersection(actual_negatives_inds))
            total_positive_hits += positive_hits
            total_negative_hits += negative_hits
            total_positives += len(actual_positives_inds)
            total_negatives += len(actual_negatives_inds)
        test_results_for_ds.append((len(dataset_loader), total_negative_hits / total_negatives,
                                    total_positive_hits / total_positives, epoch))
    neg, pos = weighted_avg_results_for_dataset(test_results_for_ds)
    return neg, pos, test_results_for_ds


def train_fold(train_datasets, test_datasets, data_folder, model, param_set, fixed_ep_test=-1,pos_weight=4):
    """

    :param train_datasets: list of train ds file names
    :param test_datasets: list of test ds file names
    :param data_folder: folder where embedding datasets are found
    :param model: initialized model object
    :param param_set: dictionary of parameters
    :param fixed_ep_test: if != -1, test after this many epochs (used in nested-cv, when number of epochs to train is
                          tuned on the training set
    :param pos_weight: the loss weight for positive samples
    :return: dictionary with maximum results TODO return the model and test it in nested-cv case
    """
    lr, patience, use_aa_len = param_set['lr'], param_set['patience'], param_set['use_aa_len']
    optimizer = optim.Adam(lr=lr, params=model.parameters(), weight_decay=0.2)

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    model = model.to(device)

    convergence_condition = False
    max_avg_pos_neg, max_results, epoch, max_pos, max_neg, epochs_trained = 0, {}, -1, 0, 0, 0
    while not convergence_condition:
        epoch += 1
        model.train()
        for train_ds in train_datasets:
            dataset = BinarySPDataset(data_folder + train_ds, use_aa_len=use_aa_len)
            dataset_loader = torch.utils.data.DataLoader(dataset,
                                                         batch_size=64, shuffle=True,
                                                         num_workers=4)
            for ind, batch in enumerate(dataset_loader):
                x, y = batch['emb'], batch['lbl']
                weights = torch.ones(y.shape) + y * (pos_weight-1)
                criterion = nn.BCELoss(weight=weights).to(device)
                x, y = x.to(device,dtype=torch.float32), y.to(device).to(torch.float)
                if use_aa_len != 200:
                    x = x[:, :use_aa_len, :]
                preds = model(x.permute(0, 2, 1))
                optimizer.zero_grad()
                loss = criterion(preds.reshape(-1), y)
                loss.backward()
                optimizer.step()
        if fixed_ep_test != -1 and fixed_ep_test == epoch:
            neg, pos, test_results_for_ds = get_pos_neg_for_datasets(test_datasets, model, data_folder, use_aa_len,
                                                                     epoch)
            avg_pos_neg = neg * 1 / 3 + pos * 2 / 3
            max_avg_pos_neg, max_neg, max_pos, max_results = avg_pos_neg, neg, pos, test_results_for_ds
        else:
            neg, pos, test_results_for_ds = get_pos_neg_for_datasets(test_datasets, model, data_folder, use_aa_len,
                                                                     epoch)
            # average results between positive and negative accuracies is taken into account, with more weight on the
            # positive labels
            avg_pos_neg = neg * 1/3 + pos * 2/3
            if avg_pos_neg < max_avg_pos_neg:
                patience -= 1
            else:
                max_avg_pos_neg, max_neg, max_pos, max_results = avg_pos_neg, neg, pos, test_results_for_ds
        print("Results for epoch {} (pos/neg acc/avg_pos_neg): {}/{}/{}".format(epoch, pos, neg, avg_pos_neg))
        convergence_condition = patience == 0 or (fixed_ep_test == epoch and fixed_ep_test != -1)

    return max_results


def init_model(ntoken, partitions,lbl2ind={}):
    model = TransformerModel(ntoken=ntoken, d_model=1024, nhead=8,
                             d_hid=1024, nlayers=3,  partitions=partitions,lbl2ind=lbl2ind)
    for p in model.parameters():
        if p.dim() > 1:
            nn.init.xavier_uniform_(p)
    return model


def train_test_folds(run_name, train_datasets_per_fold, test_datasets_per_fold, data_folder, param_set, nested=False,
                     fixed_epoch=-1, pos_weight=1):
    """
    :param run_name: save name
    :param train_datasets_per_fold: list of training dataset filenames
    :param test_datasets_per_fold: list of testing dataset filenames
    :param data_folder: path to where the datasets are found
    :param param_set: the current parameter set
    :param nested: if nested, the model is not train-testing on the outer cross-val set. The testing is also done on a
                    separate test set, used to select the best model. The final results will then be saved from the
                    outer test fold-loop
    :param fixed_epoch: when != -1, the model training does not use patience, but rather train of this ammount of epochs.
                        used in nested-cv: after the best set of params is found in the inner-cv loop, along with the
                        hyperparameters, the number of epochs it was trained for is also returned (that is also tuned with
                        patience) and that is the fixed_epoch parameter
    :param pos_weight: the weight given for positive samples of the dataset
    :return: list containing (number_of_datapoints, negative_acc, pos_acc, epoch)
    """
    results_over_all_ds = []
    for ind, (train_datasets, test_datasets) in enumerate(zip(train_datasets_per_fold,
                                                              test_datasets_per_fold)):
        model = init_model(param_set)
        max_results = train_fold(train_datasets, test_datasets, data_folder, model, param_set, pos_weight=pos_weight,
                                 fixed_ep_test=fixed_epoch)
        if not nested:
            pickle.dump([train_datasets, test_datasets, max_results], open("{}_results_on_fold_{}.bin".
                                                                           format(run_name, ind), "wb"))
        results_over_all_ds.extend(max_results)
    return results_over_all_ds


def split_train_test(train_datasets):
    """
    Function used to further split the training datasets into 4-folds of 75% training, 25% test data  for nested-cv
    :param train_datasets:
    :return:
    """
    test_ds_number = int(0.25 * len(train_datasets))
    remaining_ds = len(train_datasets) - test_ds_number * 4
    number_of_test_ds_per_fold = []
    train_ds_subfold, test_ds_subfold = [], []
    for i in range(4):
        if remaining_ds:
            number_of_test_ds_per_fold.append(test_ds_number + 1)
            remaining_ds -= 1
        else:
            number_of_test_ds_per_fold.append(test_ds_number)
    remaining_untested_datasets = set(train_datasets)
    ind = 0
    while remaining_untested_datasets:
        current_test_ds_subfold = random.sample(remaining_untested_datasets, number_of_test_ds_per_fold[ind])
        current_train_ds_subfold = list(set(train_datasets) - set(current_test_ds_subfold))
        ind += 1
        remaining_untested_datasets = remaining_untested_datasets - set(current_test_ds_subfold)
        test_ds_subfold.append(current_test_ds_subfold)
        train_ds_subfold.append(current_train_ds_subfold)
    return train_ds_subfold, test_ds_subfold


def get_avg_results_for_fold(results):
    total_ds_counts = sum([results[i][0] for i in range(len(results))])
    weights = [results[i][0] / total_ds_counts for i in range(len(results))]
    negative_results = sum([results[i][1] * weights[i] for i in range(len(results))])
    positive_results = sum([results[i][2] * weights[i] for i in range(len(results))])
    avg_epoch = int(np.mean([results[i][3] for i in range(len(results))]))
    return negative_results, positive_results, avg_epoch


def train_test_nested_folds(run_name, params, train_ds, test_ds, data_folder, param_set_number):
    best_param, best_result = None, 0
    # move over all 80%/20% train/test splits
    best_pos, best_results_params_and_epoch = 0, []
    for ind, (train_datasets, test_datasets) in enumerate(zip(train_ds,
                                                              test_ds)):
        for param_set in params:
            # further split into 4 folds of 75%/25% the training set
            print("Training parameter set {}...".format(param_set))
            train_ds_subfold, test_ds_subfold = split_train_test(train_datasets)
            max_results = train_test_folds(run_name, train_ds_subfold, test_ds_subfold, data_folder, param_set,
                                           nested=True, pos_weight=param_set['pos_weight'])

            current_neg, current_pos, train_epochs = get_avg_results_for_fold(max_results)
            if best_pos < current_pos:
                best_pos = current_pos
                best_results_params_and_epoch = [param_set, train_epochs]
            if param_set_number != -1:
                # this means that the program will run o given set of hyperparameters for the inner loops created from
                # each ouetr-loop cv train set. This should then be put together from multiple machines at the end
                # so that the maximum out of all hyperparameters will be taken into account when testing on the final
                # (validation - outer loop test set)
                result_file_name = "results_fold_{}{}.bin".format(ind, "_" + str(param_set_number))
                if os.path.exists(result_file_name):
                    all_results = pickle.load(open(result_file_name, "rb"))
                else:
                    all_results = []
                all_results.append([current_neg, current_pos, param_set, train_epochs])
                pickle.dump(all_results, open(result_file_name, "wb"))
                print("Results for param set {} after {} epochs (neg/pos):{}/{}".
                      format(param_set, train_epochs, current_neg, current_pos))
        if param_set_number == -1:
            # if the hyperparamter search is done on one machine, just save the best results for each given test-fold
            # validation
            print("final best parameters:", best_results_params_and_epoch)
            model = init_model(best_results_params_and_epoch[0])
            final_result_current_fold = train_fold(model=model, train_datasets=train_datasets, test_datasets=test_datasets,
                                                   param_set=best_results_params_and_epoch[0],
                                                   fixed_ep_test=best_results_params_and_epoch[1],
                                                   data_folder=data_folder)
            print(final_result_current_fold, best_results_params_and_epoch)
            # saves as  [len(dataset), negative_result, positive_result, epoch)]
            pickle.dump([final_result_current_fold, best_results_params_and_epoch],
                        open("results_fold_{}{}.bin".format(ind, "_" + str(param_set_number) if
                        param_set_number != -1 else ""), "wb"))

def get_data_folder():
    if os.path.exists("/scratch/work/dumitra1"):
        return "/scratch/work/dumitra1/sp_data/"
    elif os.path.exists("/home/alex"):
        return "sp_data/"
    else:
        return "/scratch/project2003818/dumitra1/sp_data/"

def get_all_ds(ds):
    ds_set = set()
    for d in ds:
        ds_set.update(d)
    return list(ds_set)

def get_all_bench_ds():
    data_folder =get_data_folder()
    test_datasets = []
    for f in os.listdir(data_folder):
        if "raw_sp6_bench_data_" in f:
            test_datasets.append(f)
    return test_datasets

def padd_add_eos_tkn(lbl_seqs, lbl2ind):
    device=torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    max_len = max([len(l) for l in lbl_seqs])
    label_outpus_tensors = []
    for l_s in lbl_seqs:
        tokenized_seq = []
        tokenized_seq.extend(l_s)
        tokenized_seq.append(lbl2ind["ES"])
        tokenized_seq.extend([lbl2ind["PD"]] * (1 + max_len - len(tokenized_seq)))
        label_outpus_tensors.append(torch.tensor(tokenized_seq, device=device))
    return torch.vstack(label_outpus_tensors)

def generate_square_subsequent_mask(sz):
    mask = (torch.triu(torch.ones((sz, sz))) == 1).transpose(0, 1)
    mask = mask.float().masked_fill(mask == 0, float('-inf')).masked_fill(mask == 1, float(0.0))
    return mask


def greedy_decode(model, src, start_symbol, lbl2ind,tgt=None):
    ind2lbl = {v:k for k,v in lbl2ind.items()}
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    src = src
    seq_len = len(src[0])
    memory = model.encode(src)
    # ys = torch.ones(1, 1).fill_(start_symbol).type(torch.long).to(device)
    ys = [[]]
    preds = []
    for i in range(seq_len):
        tgt_mask = (generate_square_subsequent_mask(len(ys[0]) + 1))
        out = model.decode(ys, memory.to(device), tgt_mask.to(device))
        out = out.transpose(0, 1)
        prob = model.generator(out[:, -1])
        _, next_word = torch.max(prob, dim=1)
        next_word = next_word.item()
        current_ys = ys[0]
        current_ys.append(next_word)
        ys = [current_ys]
        # ys = torch.cat([ys, torch.ones(1, 1, device=device).fill_(next_word)], dim=0)

    return ys

def translate(model: torch.nn.Module, src: str, bos_id, lbl2ind, tgt=None):
    model.eval()
    num_tokens = len(src)
    tgt_tokens = greedy_decode(
        model,  src, start_symbol=bos_id, lbl2ind=lbl2ind, tgt=tgt)
    return tgt_tokens

def evaluate(model, lbl2ind):
    print("Beginning evaluate")
    logging.info("Beginning evaluate")
    eval_dict = {}
    model.eval()
    losses = 0
    sp_data = SPCSpredictionData(lbl2ind=lbl2ind)
    sp_dataset = CSPredsDataset(sp_data.lbl2ind, partitions=[2], data_folder=sp_data.data_folder)

    dataset_loader = torch.utils.data.DataLoader(sp_dataset,
                                                 batch_size=1, shuffle=True,
                                                 num_workers=4, collate_fn=collate_fn)
    ind2lbl = {v:k for k,v in lbl2ind.items()}
    for ind, (src, tgt) in enumerate(dataset_loader):
        src = src
        tgt = tgt
        tgt_tokens = translate(model, src, lbl2ind['BS'], lbl2ind, tgt=tgt)
        model_output = "".join([ind2lbl[i] for i in tgt_tokens[0]])
        # print("".join([ind2lbl[i] for i in tgt_tokens[0]]), len("".join([ind2lbl[i] for i in tgt_tokens[0]])))
        # print("".join([ind2lbl[i] for i in tgt[0]]), len("".join([ind2lbl[i] for i in tgt[0]])))
        # print("\n")
        eval_dict[src] = model_output
    pickle.dump(eval_dict, open("results.bin", "wb"))


def train_cs_predictors():

    sp_data = SPCSpredictionData()
    sp_dataset = CSPredsDataset(sp_data.lbl2ind, partitions=[0,1], data_folder=sp_data.data_folder)
    dataset_loader = torch.utils.data.DataLoader(sp_dataset,
                                                 batch_size=64, shuffle=True,
                                                 num_workers=4, collate_fn=collate_fn)
    print(len(sp_data.lbl2ind.keys()))
    model = init_model(len(sp_data.lbl2ind.keys()), partitions=[0,1], lbl2ind=sp_data.lbl2ind)

    loss_fn = torch.nn.CrossEntropyLoss(ignore_index=sp_data.lbl2ind["PD"], reduction='none')

    optimizer = torch.optim.Adam(model.parameters(), lr=0.00001, betas=(0.9, 0.98), eps=1e-9)
    ind2lbl = {ind:lbl for lbl, ind in sp_data.lbl2ind.items()}
    for e in range(50):
        losses = 0
        for ind, batch in enumerate(dataset_loader):
            model.eval()

            seqs, lbl_seqs = batch
            max_len_s = 0
            some_s = 0
            logits = model(seqs, lbl_seqs)

            optimizer.zero_grad()
            targets = padd_add_eos_tkn(lbl_seqs, sp_data.lbl2ind)
            loss = loss_fn(logits.transpose(0, 1).reshape(-1, logits.shape[-1]), targets.reshape(-1))
            loss = torch.mean(loss)

            # if ind % 100 == 0:
            #
            #     print("".join([str(ind2lbl[i.item()]) for i in torch.argmax(logits.transpose(1,0),dim=-1)[0]]),"\n",
            #
            #           "".join([str(ind2lbl[i.item()]) for i in padd_add_eos_tkn(lbl_seqs, sp_data.lbl2ind)[0]]), "\n\n")
            #     print(loss)
            loss.backward()

            optimizer.step()
            losses += loss.item()
        print("On epoch {} total loss: {}".format(e, losses / len(dataset_loader)))
        logging.info("On epoch {} total loss: {}".format(e, losses / len(dataset_loader)))
    evaluate(model, sp_data.lbl2ind)

        # loss = loss_fn(logits.reshape(-1, logits.shape[-1]), tgt_out.reshape(-1))
        # loss.backward()
        #
        # optimizer.step()
        # losses += loss.item()

