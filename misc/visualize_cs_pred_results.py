from io import StringIO
import requests as r

import torch.nn
from scipy import stats
import matplotlib.pyplot as plt
from sklearn.metrics import matthews_corrcoef as compute_mcc
import os
import pickle
from Bio import SeqIO
import numpy as np

def clean_sec_sp2_preds(seq, preds):
    last_l_ind = preds.rfind("L")
    min_i = 10
    for i in range(-2,3):
        if seq[last_l_ind + i + 1] == "C":
            if np.abs(i) < np.abs(min_i):
                best_ind = i
                min_i = i
    if min_i == 0:
        return preds
    elif min_i == 10:
        return preds.replace("L", "T")
    elif min_i > 0:
        return preds[:last_l_ind] + min_i * "L" + preds[last_l_ind + min_i:]
    elif min_i < 0:
        return preds[:last_l_ind + min_i] + np.abs(min_i) * preds[last_l_ind+1] + preds[last_l_ind+np.abs(min_i):]


def get_cs_acc(life_grp, seqs, true_lbls, pred_lbls, v=False, only_cs_position=False, sp_type="SP", sptype_preds=None):
    def get_acc_for_tolerence(ind, t_lbl, sp_letter):
        true_cs = 0
        while t_lbl[true_cs] == sp_letter and true_cs < len(t_lbl):
            true_cs += 1
        if np.abs(true_cs - ind) == 0:
            return np.array([1, 1, 1, 1, 1, 0, 0, 0, 0, 0])
        elif np.abs(true_cs - ind) == 1:
            return np.array([0, 1, 1, 1, 1, 0, 1, 0, 0, 0])
        elif np.abs(true_cs - ind) == 2:
            return np.array([0, 0, 1, 1, 1, 0, 1, 1, 0, 0])
        elif np.abs(true_cs - ind) == 3:
            return np.array([0, 0, 0, 1, 1, 0, 1, 1, 1, 0])
        elif ind != 0:
            # if ind==0, SP was predicted, but CS prediction is off for all tolerence levels, meaning it's a false positive
            # if ind != 0, and teh corresponding SP was predicted, this becomes a false positive on CS predictions for all
            # tolerance levels
            return np.array([0, 0, 0, 0, 1, 0, 1, 1, 1, 1])
        else:
            # if ind==0, SP was not even predicted (so there is no CS prediction) and this affects precision metric
            # tp/(tp+fp). It means this a fn
            return np.array([0, 0, 0, 0, 1, 0, 0, 0, 0, 0])

    ind2glbl_lbl = {0: 'NO_SP', 1: 'SP', 2: 'TATLIPO', 3: 'LIPO', 4: 'TAT', 5: 'PILIN'}
    glbllbl2_ind = {v:k for k,v in ind2glbl_lbl.items()}
    sptype2letter = {'TAT': 'T', 'LIPO': 'L', 'PILIN': 'P', 'TATLIPO': 'T', 'SP': 'S'}
    sp_types = ["S", "T", "L", "P"]
    # S = signal_peptide; T = Tat/SPI or Tat/SPII SP; L = Sec/SPII SP; P = SEC/SPIII SP; I = cytoplasm; M = transmembrane; O = extracellular;
    # order of elemnts in below list:
    # (eukaria_correct_tollerence_0, eukaria_correct_tollerence_1, eukaria_correct_tollerence_2, ..3, eukaria_total, eukaria_all_pos_preds)
    # (negative_correct_tollerence_0, negative_correct_tollerence_1, negative_correct_tollerence_2, ..3, negative_total, negative_all_pos_preds)
    # (positive_correct_tollerence_0, positive_correct_tollerence_1, positive_correct_tollerence_2, ..3, positive_total, positive_all_pos_preds)
    # (archaea_correct_tollerence_0, archaea_correct_tollerence_1, archaea_correct_tollerence_2, ..3, archaea_total, archae_all_pos_preds)
    # We used precision and recall to assess CS predictions, where precision is defined as the fraction of CS predictions
    # that are correct, and recall is the fraction of real SPs that are predicted as the correct SP type and have the correct CS assigned.
    grp2_ind = {"EUKARYA": 0, "NEGATIVE": 1, "POSITIVE": 2, "ARCHAEA": 3}
    predictions = [[0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                   [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]]
    predictions = [np.array(p) for p in predictions]
    count, count2 = 0, 0
    count_tol_fn, count_complete_fn, count_otherSPpred = 0, 0, 0
    sp_letter = sptype2letter[sp_type]
    cnt1, cnt2 = 0, 0
    for l, s, t, p in zip(life_grp, seqs, true_lbls, pred_lbls):
        lg, sp_info = l.split("|")
        ind = 0
        predicted_sp = p[0]
        is_sp = predicted_sp in sp_types

        if sp_info == sp_type:
            if p[0] == t[0]:
                count += 1
            else:
                count2 += 1
            #     # the precision was defined as the fraction of correct CS predictions over the number of predicted
            #     # CS, recall as the fraction of correct CS predictions over the number of true CS. In both cases,
            #     # a CS was only considered correct if it was predicted in the correct SP class (e.g. when the
            #     # model predicts a CS in a Sec/SPI sequence, but predicts Sec/SPII as the sequence label, the
            #     # sample is considered as no CS predicted).

            # SO ONLY CONSIDER IT AS A FALSE NEGATIVE FOR THE APPROPRIATE correct-SP class?
            if (sptype_preds is not None and ind2glbl_lbl[sptype_preds[s]] == sp_type) or (sptype_preds is None and sp_letter == p[ind]):
                while (p[ind] == sp_letter or (p[ind] == predicted_sp and is_sp and only_cs_position)) and ind < len(p) - 1:
                    # when only_cs_position=True, the cleavage site positions will be taken into account irrespective of
                    # whether the predicted SP is the correct kind
                    ind += 1
            else:
                ind = 0
            predictions[grp2_ind[lg]] += get_acc_for_tolerence(ind, t, sp_letter)
        # elif sp_info != sp_type and   p[ind] == sp_letter:
        elif (sptype_preds is not None and sp_info != sp_type and ind2glbl_lbl[sptype_preds[s]] == sp_type) or (sptype_preds is None and p[ind] == sp_letter):
            predictions[grp2_ind[lg]] += np.array([0, 0, 0, 0, 0, 0, 1, 1, 1, 1])
    if v:
        print(" count_tol_fn, count_complete_fn, count_otherSPpred", count_tol_fn, count_complete_fn, count_otherSPpred)
    print(sp_type, "count, count2", count, count2 )
    print(cnt1, cnt2)
    all_recalls = []
    all_precisions = []
    all_f1_scores = []
    total_positives = []
    false_positives = []
    for life_grp, ind in grp2_ind.items():
        if sp_type == "SP" or life_grp != "EUKARYA":
            # eukaryotes do not have SEC/SPI or SEC/SPII
            current_preds = predictions[grp2_ind[life_grp]]
            if v:
                print("Recall {}: {}".format(life_grp, [current_preds[i] / current_preds[4] for i in range(4)]))
                print("Prec {}: {}".format(life_grp,
                                           [current_preds[i] / (current_preds[i] + current_preds[5]) for i in
                                            range(4)]))
            all_recalls.append([current_preds[i] / current_preds[4] for i in range(4)])
            all_precisions.append([])
            all_f1_scores.append([])
            for i in range(4):
                if current_preds[5] + current_preds[i] == 0:
                    all_precisions[-1].append(0.)
                else:
                    all_precisions[-1].append(
                        current_preds[i] / (current_preds[i] + current_preds[i + 6]))
            current_recs, current_precs = all_recalls[-1], all_precisions[-1]
            all_f1_scores[-1].extend([0 if current_recs[i] * current_precs[i] == 0 else 2 * current_recs[i] *
                                                                                        current_precs[i] / (
                                                                                                    current_recs[i] +
                                                                                                    current_precs[i])
                                      for i in range(4)])
            total_positives.append(current_preds[4])
            false_positives.append(current_preds[5])
    return all_recalls, all_precisions, total_positives, false_positives, predictions, all_f1_scores


def get_class_sp_accs(life_grp, seqs, true_lbls, pred_lbls):
    groups_tp_tn_fp_fn = [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    grp2_ind = {"EUKARYA": 0, "NEGATIVE": 1, "POSITIVE": 2, "ARCHAEA": 3}
    for lg, s, tl, pl in zip(life_grp, seqs, true_lbls, pred_lbls):
        lg = lg.split("|")[0]
        if tl[0] == pl[0] and tl[0] == "S":
            groups_tp_tn_fp_fn[grp2_ind[lg]][0] += 1
        elif tl[0] != "S" and pl[0] != "S":
            groups_tp_tn_fp_fn[grp2_ind[lg]][1] += 1
        elif tl[0] == "S" and pl[0] != "S":
            groups_tp_tn_fp_fn[grp2_ind[lg]][3] += 1
        elif tl[0] != "S" and pl[0] == "S":
            groups_tp_tn_fp_fn[grp2_ind[lg]][2] += 1
    recs = [groups_tp_tn_fp_fn[i][0] / (groups_tp_tn_fp_fn[i][0] + groups_tp_tn_fp_fn[i][3]) if
            groups_tp_tn_fp_fn[i][0] + groups_tp_tn_fp_fn[i][3] != 0 else 0 for i in range(4)]
    precs = [groups_tp_tn_fp_fn[i][0] / (groups_tp_tn_fp_fn[i][0] + groups_tp_tn_fp_fn[i][2]) if
             groups_tp_tn_fp_fn[i][0] + groups_tp_tn_fp_fn[i][2] != 0 else 0 for i in range(4)]
    return [ (2 * recs[i] * precs[i]) / (precs[i] + recs[i]) if precs[i] + recs[i] != 0 else 0 for i in range(4)]


def get_pred_accs_sp_vs_nosp(life_grp, seqs, true_lbls, pred_lbls, v=False, return_mcc2=False, sp_type="SP", sptype_preds=None):
    # S = signal_peptide; T = Tat/SPI or Tat/SPII SP; L = Sec/SPII SP; P = SEC/SPIII SP; I = cytoplasm; M = transmembrane; O = extracellular;
    # order of elemnts in below list:
    # (eukaria_tp, eukaria_tn, eukaria_fp, eukaria_fn)
    # (negative_tp, negative_tn, negative_fp, negative_fn)
    # (positive_tp, positive_tn, positive_fp, positive_fn)
    # (archaea_correct, archaea_total)
    # Matthews correlation coefficient (MCC) both true and false positive and negative predictions are counted at
    # the sequence level
    grp2_ind = {"EUKARYA": 0, "NEGATIVE": 1, "POSITIVE": 2, "ARCHAEA": 3}
    lg2sp_letter = {'TAT': 'T', 'LIPO': 'L', 'PILIN': 'P', 'TATLIPO': 'T', 'SP': 'S'}
    sp_type_letter = lg2sp_letter[sp_type]
    predictions = [[[], []], [[], []], [[], []], [[], []]]
    predictions_mcc2 = [[[], []], [[], []], [[], []], [[], []]]
    zv = 0
    for l, s, t, p in zip(life_grp, seqs, true_lbls, pred_lbls):
        zv += 1
        lg, sp_info = l.split("|")
        if sp_info == sp_type or sp_info == "NO_SP":
            p = p.replace("ES", "J")
            len_ = min(len(p), len(t))
            t, p = t[:len_], p[:len_]
            for ind in range(len(t)):
                if t[ind] == sp_type_letter and p[ind] == sp_type_letter:
                    predictions[grp2_ind[lg]][1].append(1)
                    predictions[grp2_ind[lg]][0].append(1)
                elif t[ind] == sp_type_letter and p[ind] != sp_type_letter:
                    predictions[grp2_ind[lg]][1].append(1)
                    predictions[grp2_ind[lg]][0].append(-1)
                elif t[ind] != sp_type_letter and p[ind] == sp_type_letter:
                    predictions[grp2_ind[lg]][1].append(-1)
                    predictions[grp2_ind[lg]][0].append(1)
                elif t[ind] != sp_type_letter and p[ind] != sp_type_letter:
                    predictions[grp2_ind[lg]][1].append(-1)
                    predictions[grp2_ind[lg]][0].append(-1)
        if return_mcc2:
            p = p.replace("ES", "J")
            len_ = min(len(p), len(t))
            t, p = t[:len_], p[:len_]
            for ind in range(len(t)):
                if t[ind] == sp_type_letter and p[ind] == sp_type_letter:
                    predictions_mcc2[grp2_ind[lg]][1].append(1)
                    predictions_mcc2[grp2_ind[lg]][0].append(1)
                elif t[ind] == sp_type_letter and p[ind] != sp_type_letter:
                    predictions_mcc2[grp2_ind[lg]][1].append(1)
                    predictions_mcc2[grp2_ind[lg]][0].append(-1)
                elif t[ind] != sp_type_letter and p[ind] == sp_type_letter:
                    predictions_mcc2[grp2_ind[lg]][1].append(-1)
                    predictions_mcc2[grp2_ind[lg]][0].append(1)
                elif t[ind] != sp_type_letter and p[ind] != sp_type_letter:
                    predictions_mcc2[grp2_ind[lg]][1].append(-1)
                    predictions_mcc2[grp2_ind[lg]][0].append(-1)
    mccs, mccs2 = [], []
    for grp, id in grp2_ind.items():
        if sp_type == "SP" or grp != "EUKARYA":
            if sum(predictions[grp2_ind[grp]][0]) == -len(predictions[grp2_ind[grp]][0]) or \
                    sum(predictions[grp2_ind[grp]][0]) == len(predictions[grp2_ind[grp]][0]):
                mccs.append(-1)
            else:
                mccs.append(compute_mcc(predictions[grp2_ind[grp]][0]
                                        , predictions[grp2_ind[grp]][1]))
            if v:
                print("{}: {}".format(grp, mccs[-1]))
    if return_mcc2:
        for grp, id in grp2_ind.items():
            if sp_type == "SP" or grp != "EUKARYA":

                if sum(predictions_mcc2[grp2_ind[grp]][0]) == -len(predictions_mcc2[grp2_ind[grp]][0]) or \
                        sum(predictions_mcc2[grp2_ind[grp]][0]) == len(predictions_mcc2[grp2_ind[grp]][0]):
                    mccs2.append(-1)
                else:
                    mccs2.append(compute_mcc(predictions_mcc2[grp2_ind[grp]][0]
                                             , predictions_mcc2[grp2_ind[grp]][1]))
                if v:
                    print("{}: {}".format(grp, mccs2[-1]))
        return mccs, mccs2
    return mccs


def get_bin(p, bins):
    for i in range(len(bins)):
        if bins[i] < p <= bins[i + 1]:
            return i


def get_cs_preds_by_tol(tl, pl):
    pl = pl.replace("ES", "")
    correct_by_tol = [0, 0, 0, 0]
    for tol in range(4):
        correct_by_tol[tol] = int(tl.rfind("S") - tol <= pl.rfind("S") <= tl.rfind("S") + tol)
    return correct_by_tol


def plot_reliability_diagrams(resulted_perc_by_acc, name, total_counts_per_acc):
    import matplotlib
    fig = matplotlib.pyplot.gcf()
    fig.set_size_inches(12, 8)
    fig.savefig('test2png.png', dpi=100)

    accs = [acc_to_perc[0] for acc_to_perc in resulted_perc_by_acc]
    total_counts_per_acc = list(total_counts_per_acc)
    percs = [acc_to_perc[1] for acc_to_perc in resulted_perc_by_acc]
    bars_width = accs[0] - accs[1]
    plt.title(name)
    plt.bar(accs, accs, width=bars_width, alpha=0.5, linewidth=2, edgecolor="black", color='blue',
            label='Perfect calibration')
    plt.bar(accs, percs, width=bars_width, alpha=0.5, color='red', label="Model's calibration",
            tick_label=["{}\n{}".format(str(round(accs[i], 2)), str(total_counts_per_acc[i])) for i in
                        range(len(accs))])
    plt.xlabel("Prob/No of preds")
    plt.ylabel("Prob")
    plt.legend()
    plt.show()


def get_prob_calibration_and_plot(probabilities_file="", life_grp=None, seqs=None, true_lbls=None, pred_lbls=None,
                                  bins=15, plot=True, sp2probs=None):
    # initialize bins
    bin_limmits = np.linspace(0, 1, bins)
    correct_calibration_accuracies = [(bin_limmits[i] + bin_limmits[i + 1]) / 2 for i in range(bins - 1)]

    # initialize cleavage site and binary sp dictionaries of the form:
    # binary_sp_dict: {<life_group> : { total : { <accuracy> : count }, correct : { <accuracy> : count} } }
    # cs_pred: {<life_group> : { <tol> : { total : {<accuracy> : count}, correct: {<accuracy> : count} } } }
    binary_sp_calibration_by_grp = {}
    cs_by_lg_and_tol_accs = {}
    for lg in life_grp:
        lg = lg.split("|")[0]
        crct_cal_acc_2_correct_preds = {crct_cal_acc: 0 for crct_cal_acc in correct_calibration_accuracies}
        crct_cal_acc_2_totals = {crct_cal_acc: 0 for crct_cal_acc in correct_calibration_accuracies}
        wrap_dict = {'total': crct_cal_acc_2_totals, 'correct': crct_cal_acc_2_correct_preds}
        binary_sp_calibration_by_grp[lg] = wrap_dict
        tol_based_cs_accs = {}
        for tol in range(4):
            crct_cal_acc_2_correct_preds = {crct_cal_acc: 0 for crct_cal_acc in correct_calibration_accuracies}
            crct_cal_acc_2_totals = {crct_cal_acc: 0 for crct_cal_acc in correct_calibration_accuracies}
            wrap_dict = {'total': crct_cal_acc_2_totals, 'correct': crct_cal_acc_2_correct_preds}
            tol_based_cs_accs[tol] = wrap_dict
        cs_by_lg_and_tol_accs[lg] = tol_based_cs_accs

    sp2probs = pickle.load(open(probabilities_file, "rb")) if sp2probs is None else sp2probs
    for s, tl, pl, lg in zip(seqs, true_lbls, pred_lbls, life_grp):
        lg = lg.split("|")[0]
        predicted_sp_prob, all_sp_probs, _ = sp2probs[s]
        bin = get_bin(predicted_sp_prob, bin_limmits)
        coresp_acc = correct_calibration_accuracies[bin]
        if tl[0] == "S":
            binary_sp_calibration_by_grp[lg]['total'][coresp_acc] += 1
            if pl[0] == "S":
                binary_sp_calibration_by_grp[lg]['correct'][coresp_acc] += 1
        if tl[0] == pl[0] == "S":
            correct_preds_by_tol = get_cs_preds_by_tol(tl, pl)
            for tol in range(4):
                cs_by_lg_and_tol_accs[lg][tol]['correct'][coresp_acc] += correct_preds_by_tol[tol]
                cs_by_lg_and_tol_accs[lg][tol]['total'][coresp_acc] += 1
    binary_ece, cs_ece = [], [[], [], [], []]
    for lg_ind, lg in enumerate(['EUKARYA', 'NEGATIVE', 'POSITIVE', 'ARCHAEA']):
        correct_binary_preds, total_binary_preds = binary_sp_calibration_by_grp[lg]['correct'].values(), \
                                                   binary_sp_calibration_by_grp[lg]['total'].values()
        results = []
        current_binary_ece = []
        for ind, (crct, ttl) in enumerate(zip(correct_binary_preds, total_binary_preds)):
            actual_acc = crct / ttl if ttl != 0 else 0
            results.append((correct_calibration_accuracies[ind], actual_acc if ttl != 0 else 0))
            current_binary_ece.append(
                np.abs(correct_calibration_accuracies[ind] - actual_acc) * (ttl / sum(total_binary_preds)))
        binary_ece.append(round(sum(current_binary_ece), 3))
        if plot:
            print("Binary preds for {} with ECE {}: ".format(lg, sum(current_binary_ece)), results, total_binary_preds)
            plot_reliability_diagrams(results, "Binary sp pred results for {} with ECE {}".format(lg, round(
                sum(current_binary_ece), 3)), total_binary_preds)
        for tol in range(4):
            correct_cs_preds, total_cs_preds = cs_by_lg_and_tol_accs[lg][tol]['correct'].values(), \
                                               cs_by_lg_and_tol_accs[lg][tol]['total'].values()
            results = []
            current_cs_ece = []
            for ind, (crct, ttl) in enumerate(zip(correct_cs_preds, total_cs_preds)):
                results.append((correct_calibration_accuracies[ind], crct / ttl if ttl != 0 else 0))
                actual_acc = crct / ttl if ttl != 0 else 0
                current_cs_ece.append(
                    np.abs(correct_calibration_accuracies[ind] - actual_acc) * (ttl / sum(total_binary_preds)))
            cs_ece[lg_ind].append(round(sum(current_cs_ece), 3))
            if plot:
                plot_reliability_diagrams(results, "CS pred results for tol {} for {} with ECE {}".format(tol, lg,
                                                                                                          round(
                                                                                                              sum(current_cs_ece),
                                                                                                              3)),
                                          total_cs_preds)
                print("Cs preds for {} for tol {}:".format(lg, tol), results)


def extract_seq_group_for_predicted_aa_lbls(filename="run_wo_lg_info.bin", test_fold=2, dict_=None):
    seq2preds = pickle.load(open(filename, "rb")) if dict_ is None else dict_
    tested_seqs = set(seq2preds.keys())
    seq2id = {}
    life_grp, seqs, true_lbls, pred_lbls = [], [], [], []
    for seq_record in SeqIO.parse(get_data_folder() + "sp6_data/train_set.fasta", "fasta"):
        seq, lbls = seq_record.seq[:len(seq_record.seq) // 2], seq_record.seq[len(seq_record.seq) // 2:]
        if seq in tested_seqs:
            life_grp.append("|".join(str(seq_record.id).split("|")[1:-1]))
            seqs.append(seq)
            true_lbls.append(lbls)
            pred_lbls.append(seq2preds[seq])
    return life_grp, seqs, true_lbls, pred_lbls


def get_data_folder():
    if os.path.exists("sp6_data/"):
        return "./"
    elif os.path.exists("results"):
        return "../sp_data/"
    elif os.path.exists("/scratch/work/dumitra1"):
        return "/scratch/work/dumitra1/sp_data/"
    elif os.path.exists("/home/alex"):
        return "sp_data/"
    else:
        return "/scratch/project2003818/dumitra1/sp_data/"


def get_cs_and_sp_pred_results(filename="run_wo_lg_info.bin", v=False, probabilities_file=None, return_everything=False,
                               return_class_prec_rec=False,):
    sptype_filename = filename.replace(".bin", "")  + "_sptype.bin"
    if os.path.exists(sptype_filename):
        sptype_preds = pickle.load(open(sptype_filename, "rb"))
    else:
        sptype_preds = None
    life_grp, seqs, true_lbls, pred_lbls = extract_seq_group_for_predicted_aa_lbls(filename=filename)
    if probabilities_file is not None:
        get_prob_calibration_and_plot(probabilities_file, life_grp, seqs, true_lbls, pred_lbls)
    sp_pred_mccs = get_pred_accs_sp_vs_nosp(life_grp, seqs, true_lbls, pred_lbls, v=v)
    all_recalls, all_precisions, total_positives, \
    false_positives, predictions, all_f1_scores = get_cs_acc(life_grp, seqs, true_lbls, pred_lbls, v=v, sptype_preds=sptype_preds)
    if return_everything:
        sp_pred_mccs, sp_pred_mccs2 = get_pred_accs_sp_vs_nosp(life_grp, seqs, true_lbls, pred_lbls, v=v,
                                                               return_mcc2=True, sp_type="SP", sptype_preds=sptype_preds)
        lipo_pred_mccs, lipo_pred_mccs2 = get_pred_accs_sp_vs_nosp(life_grp, seqs, true_lbls, pred_lbls, v=v,
                                                                   return_mcc2=True, sp_type="LIPO", sptype_preds=sptype_preds)
        tat_pred_mccs, tat_pred_mccs2 = get_pred_accs_sp_vs_nosp(life_grp, seqs, true_lbls, pred_lbls, v=v,
                                                                 return_mcc2=True, sp_type="TAT", sptype_preds=sptype_preds)

        all_recalls_lipo, all_precisions_lipo, _, _, _, all_f1_scores_lipo = get_cs_acc(life_grp, seqs, true_lbls,
                                                                                        pred_lbls, v=False,
                                                                                        only_cs_position=False,
                                                                                        sp_type="LIPO", sptype_preds=sptype_preds)
        all_recalls_tat, all_precisions_tat, _, _, _, all_f1_scores_tat = get_cs_acc(life_grp, seqs, true_lbls,
                                                                                     pred_lbls, v=False,
                                                                                     only_cs_position=False,
                                                                                     sp_type="TAT", sptype_preds=sptype_preds)
        if return_class_prec_rec:
            return sp_pred_mccs, sp_pred_mccs2, lipo_pred_mccs, lipo_pred_mccs2, tat_pred_mccs, tat_pred_mccs2, \
                   all_recalls_lipo, all_precisions_lipo, all_recalls_tat, all_precisions_tat, all_f1_scores_lipo, all_f1_scores_tat, \
                   all_recalls, all_precisions, total_positives, false_positives, predictions, all_f1_scores, \
                   get_class_sp_accs(life_grp, seqs, true_lbls, pred_lbls)
        return sp_pred_mccs, sp_pred_mccs2, lipo_pred_mccs, lipo_pred_mccs2, tat_pred_mccs, tat_pred_mccs2, \
               all_recalls_lipo, all_precisions_lipo, all_recalls_tat, all_precisions_tat, all_f1_scores_lipo, all_f1_scores_tat, \
               all_recalls, all_precisions, total_positives, false_positives, predictions, all_f1_scores
    if return_class_prec_rec:
        return sp_pred_mccs, all_recalls, all_precisions, total_positives, false_positives, predictions, all_f1_scores, \
               get_class_sp_accs(life_grp, seqs, true_lbls, pred_lbls)
    return sp_pred_mccs, all_recalls, all_precisions, total_positives, false_positives, predictions, all_f1_scores


def get_summary_sp_acc(sp_pred_accs):
    return np.mean(sp_pred_accs), sp_pred_accs[0]


def get_summary_cs_acc(all_cs_preds):
    return np.mean(np.array(all_cs_preds)), np.mean(all_cs_preds[0]), all_cs_preds[0][0]


def plot_losses(losses, name="param_search_0.2_2048_0.0001_"):
    train_loss, valid_loss = losses
    fig, axs = plt.subplots(1, 1, figsize=(12, 8))

    axs.set_title("Train and validation loss over epochs")
    axs.plot(train_loss, label="Train loss")
    axs.plot(valid_loss, label="Validation loss")
    axs.set_xlabel("Epochs")
    axs.set_ylabel("Loss")
    axs.legend()
    axs.set_ylim(0, 0.2)
    # plt.savefig("/home/alex/Desktop/sp6_ds_transformer_nmt_results/" + name + "loss.png")
    plt.show()


def plot_mcc(mccs, name="param_search_0.2_2048_0.0001_"):
    euk_mcc, neg_mcc, pos_mcc, arc_mcc = mccs
    fig, axs = plt.subplots(2, 2, figsize=(12, 8))
    axs[0, 0].plot(euk_mcc, label="Eukaryote mcc")
    axs[0, 0].set_ylabel("mcc")
    axs[0, 0].set_ylim(-1.1, 1.1)
    axs[0, 0].legend()

    axs[0, 1].plot(neg_mcc, label="Negative mcc")
    axs[0, 1].set_ylim(-1.1, 1.1)
    axs[0, 1].legend()

    axs[1, 0].plot(pos_mcc, label="Positive mcc")
    axs[1, 0].legend()
    axs[1, 0].set_ylim(-1.1, 1.1)
    axs[1, 0].set_ylabel("mcc")

    axs[1, 0].set_xlabel("epochs")

    axs[1, 1].plot(arc_mcc, label="Archaea mcc")
    axs[1, 1].legend()

    axs[1, 1].set_ylim(-1.1, 1.1)
    axs[1, 1].set_xlabel("epochs")
    # plt.savefig("/home/alex/Desktop/sp6_ds_transformer_nmt_results/{}_{}.png".format(name, "mcc"))
    plt.show()


def extract_and_plot_prec_recall(results, metric="recall", name="param_search_0.2_2048_0.0001_", sp_type_f1=[[]]):
    cs_res_euk, cs_res_neg, cs_res_pos, cs_res_arc = results
    fig, axs = plt.subplots(2, 2, figsize=(12, 8))
    for i in range(4):
        axs[0, 0].plot(cs_res_euk[i], label="Eukaryote {} tol={}".format(metric, i))
        if i == 0 and metric == "f1"  and len(sp_type_f1[0]) != 0:
            axs[0, 0].plot(sp_type_f1[0], color='black', label="Eukaryote sp type F1")
        axs[0, 0].set_ylabel(metric)
        axs[0, 0].legend()
        axs[0, 0].set_ylim(-0.1, 1.1)

        axs[0, 1].plot(cs_res_neg[i], label="Negative {} tol={}".format(metric, i))
        if i == 0 and metric == "f1" and len(sp_type_f1[0]) != 0:
            axs[0, 1].plot(sp_type_f1[1], color='black' , label="Negative sp type F1")
        axs[0, 1].legend()
        axs[0, 1].set_ylim(-0.1, 1.1)

        axs[1, 0].plot(cs_res_pos[i], label="Positive {} tol={}".format(metric, i))
        if i == 0  and metric == "f1"  and len(sp_type_f1[0]) != 0:
            axs[1, 0].plot(sp_type_f1[2], color='black', label="Positive sp type F1")
        axs[1, 0].legend()
        axs[1, 0].set_xlabel("epochs")
        axs[1, 0].set_ylim(-0.1, 1.1)
        axs[1, 0].set_ylabel(metric)

        axs[1, 1].plot(cs_res_arc[i], label="Archaea {} tol={}".format(metric, i))
        if i == 0  and metric == "f1" and len(sp_type_f1[0]) != 0:
            axs[1, 1].plot(sp_type_f1[3], color='black', label="Archaea sp type F1")
        axs[1, 1].legend()
        axs[1, 1].set_xlabel("epochs")

        axs[1, 1].set_ylim(-0.1, 1.1)

    # plt.savefig("/home/alex/Desktop/sp6_ds_transformer_nmt_results/{}_{}.png".format(name, metric))
    plt.show()


def visualize_validation(run="param_search_0.2_2048_0.0001_", folds=[0, 1], folder=""):

    all_results = []
    euk_mcc, neg_mcc, pos_mcc, arc_mcc, train_loss, valid_loss, cs_recalls_euk, cs_recalls_neg, cs_recalls_pos, \
    cs_recalls_arc, cs_precs_euk, cs_precs_neg, cs_precs_pos, cs_precs_arc, sp_type_f1 = extract_results(run, folds=folds,
                                                                                                folder=folder)
    best_vl = 20
    patience = 0
    best_patience = 0
    for v_l in valid_loss:
        if v_l < best_vl:
            best_patience = patience
            best_vl = v_l
        else:
            patience -= 1
    print(best_vl, best_patience)
    all_f1 = [[[], [], [], []], [[], [], [], []], [[], [], [], []], [[], [], [], []]]
    for lg_ind, (lg_rec, lg_prec) in enumerate([(cs_recalls_euk, cs_precs_euk), (cs_recalls_neg, cs_precs_neg),
                                                (cs_recalls_pos, cs_precs_pos), (cs_recalls_arc, cs_precs_arc)]):
        for tol in range(4):
            for prec, rec in zip(lg_rec[tol], lg_prec[tol]):
                all_f1[lg_ind][tol].append(2 * prec * rec / (prec + rec) if prec + rec else 0)
    cs_f1_euk, cs_f1_neg, cs_f1_pos, cs_f1_arc = all_f1
    plot_mcc([euk_mcc, neg_mcc, pos_mcc, arc_mcc], name=run)
    plot_losses([train_loss, valid_loss], name=run)
    extract_and_plot_prec_recall([cs_f1_euk, cs_f1_neg, cs_f1_pos, cs_f1_arc], metric="f1", name=run, sp_type_f1=sp_type_f1)
    extract_and_plot_prec_recall([cs_recalls_euk, cs_recalls_neg, cs_recalls_pos, cs_recalls_arc], metric="recall",
                                 name=run)
    extract_and_plot_prec_recall([cs_precs_euk, cs_precs_neg, cs_precs_pos, cs_precs_arc], metric="precision", name=run)
    # extract_and_plot_losses(lines)


def extract_results(run="param_search_0.2_2048_0.0001_", folds=[0, 1], folder='results_param_s_2/'):
    euk_mcc, neg_mcc, pos_mcc, arc_mcc = [], [], [], []
    train_loss, valid_loss = [], []
    cs_recalls_euk, cs_recalls_neg, cs_recalls_pos, cs_recalls_arc = [[], [], [], []], [[], [], [], []], \
                                                                     [[], [], [], []], [[], [], [], []]
    cs_precs_euk, cs_precs_neg, cs_precs_pos, cs_precs_arc = [[], [], [], []], [[], [], [], []], \
                                                             [[], [], [], []], [[], [], [], []]
    class_preds = [[], [], [], []]
    with open(folder + run + "{}_{}.log".format(folds[0], folds[1]), "rt") as f:
        lines = f.readlines()
    for l in lines:
        if "sp_pred mcc" in l and "VALIDATION" in l:
            mccs = l.split(":")[-1].replace(" ", "").split(",")
            euk_mcc.append(float(mccs[0]))
            neg_mcc.append(float(mccs[1]))
            pos_mcc.append(float(mccs[2]))
            arc_mcc.append(float(mccs[3]))
        elif "train/validation" in l:
            train_l, valid_l = l.split(":")[-1].replace(" ", "").split("/")
            valid_l = valid_l.split(",")[0].replace(" ", "")
            train_l, valid_l = float(train_l), float(valid_l)
            train_loss.append(train_l)
            valid_loss.append(valid_l)
        elif "cs recall" in l and "VALIDATION" in l:
            cs_res = l.split(":")[-1].replace(" ", "").split(",")
            cs_res = [float(c_r) for c_r in cs_res]
            cs_recalls_euk[0].append(cs_res[0])
            cs_recalls_euk[1].append(cs_res[1])
            cs_recalls_euk[2].append(cs_res[2])
            cs_recalls_euk[3].append(cs_res[3])

            cs_recalls_neg[0].append(cs_res[4])
            cs_recalls_neg[1].append(cs_res[5])
            cs_recalls_neg[2].append(cs_res[6])
            cs_recalls_neg[3].append(cs_res[7])

            cs_recalls_pos[0].append(cs_res[8])
            cs_recalls_pos[1].append(cs_res[9])
            cs_recalls_pos[2].append(cs_res[10])
            cs_recalls_pos[3].append(cs_res[11])

            cs_recalls_arc[0].append(cs_res[12])
            cs_recalls_arc[1].append(cs_res[13])
            cs_recalls_arc[2].append(cs_res[14])
            cs_recalls_arc[3].append(cs_res[15])

        elif "cs precision" in l and "VALIDATION" in l:
            prec_res = l.split(":")[-1].replace(" ", "").split(",")
            prec_res = [float(c_r) for c_r in prec_res]
            cs_precs_euk[0].append(prec_res[0])
            cs_precs_euk[1].append(prec_res[1])
            cs_precs_euk[2].append(prec_res[2])
            cs_precs_euk[3].append(prec_res[3])

            cs_precs_neg[0].append(prec_res[4])
            cs_precs_neg[1].append(prec_res[5])
            cs_precs_neg[2].append(prec_res[6])
            cs_precs_neg[3].append(prec_res[7])

            cs_precs_pos[0].append(prec_res[8])
            cs_precs_pos[1].append(prec_res[9])
            cs_precs_pos[2].append(prec_res[10])
            cs_precs_pos[3].append(prec_res[11])

            cs_precs_arc[0].append(prec_res[12])
            cs_precs_arc[1].append(prec_res[13])
            cs_precs_arc[2].append(prec_res[14])
            cs_precs_arc[3].append(prec_res[15])
        elif "F1Score:" in l and "VALIDATION" in l:
            vals = l.split("F1Score:")[-1].replace(",","").split(" ")
            vals = [v for v in vals if v != '']
            vals = [float(v.replace("\n", "")) for v in vals]
            class_preds[0].append(float(vals[0]))
            class_preds[1].append(float(vals[1]))
            class_preds[2].append(float(vals[2]))
            class_preds[3].append(float(vals[3]))


    # fix for logs that have f1 score written as "precision"...
    if len(cs_precs_pos[0]) == 2 * len(cs_recalls_pos[0]):
        len_cs_rec = len(cs_recalls_pos[0])
        for j in range(4):
            cs_precs_euk[j], cs_precs_neg[j], cs_precs_pos[j], cs_precs_arc[j] = [cs_precs_euk[j][i * 2] for i in
                                                                                  range(len_cs_rec)], \
                                                                                 [cs_precs_neg[j][i * 2] for i in
                                                                                  range(len_cs_rec)], \
                                                                                 [cs_precs_pos[j][i * 2] for i in
                                                                                  range(len_cs_rec)], \
                                                                                 [cs_precs_arc[j][i * 2] for i in
                                                                                  range(len_cs_rec)]

    return euk_mcc, neg_mcc, pos_mcc, arc_mcc, train_loss, valid_loss, cs_recalls_euk, cs_recalls_neg, cs_recalls_pos, \
           cs_recalls_arc, cs_precs_euk, cs_precs_neg, cs_precs_pos, cs_precs_arc, class_preds


def remove_from_dictionary(res_dict, test_fld):
    tb_removed = pickle.load(open("../sp_data/sp6_partitioned_data_test_{}.bin".format(test_fld[0]), "rb"))
    tb_removed = tb_removed.keys()
    trimmed_res_dict = {}

    for seq, res in res_dict.items():
        if seq not in tb_removed:
            trimmed_res_dict[seq] = res
    return trimmed_res_dict


def extract_mean_test_results(run="param_search_0.2_2048_0.0001", result_folder="results_param_s_2/",
                              only_cs_position=False, remove_test_seqs=False, return_sptype_f1=False, benchmark=True):
    full_dict_results = {}
    full_sptype_dict = {}
    epochs = []
    for tr_folds in [[0, 1], [1, 2], [0, 2]]:
        with open(result_folder + run + "_{}_{}.log".format(tr_folds[0], tr_folds[1]), "rt") as f:
            lines = f.readlines()
            try:
                epochs.append(int(lines[-2].split(" ")[2]))
            except:
                epochs.append(int(lines[-2].split(":")[-3].split(" ")[-1]))
    avg_epoch = np.mean(epochs)
    id2seq, _, _, _ = extract_id2seq_dict()
    unique_bench_seqs = set(id2seq.values())
    for tr_folds in [[0, 1], [1, 2], [0, 2]]:
        res_dict = pickle.load(open(result_folder + run + "_{}_{}_best.bin".format(tr_folds[0], tr_folds[1]), "rb"))
        if benchmark:
            res_dict = {k:v for k,v in res_dict.items() if k in unique_bench_seqs}
        if os.path.exists(result_folder + run + "_{}_{}_best_sptype.bin".format(tr_folds[0], tr_folds[1])):
            sptype_dict = pickle.load(open(result_folder + run + "_{}_{}_best_sptype.bin".format(tr_folds[0], tr_folds[1]), "rb"))
            full_sptype_dict.update(sptype_dict)
        else:
            full_sptype_dict = None
        test_fld = list({0, 1, 2} - set(tr_folds))
        if remove_test_seqs:
            full_dict_results.update(remove_from_dictionary(res_dict, test_fld))
        else:
            full_dict_results.update(res_dict)
    print(len(full_dict_results.keys()), len(set(full_dict_results.keys())), len(unique_bench_seqs))
    life_grp, seqs, true_lbls, pred_lbls = extract_seq_group_for_predicted_aa_lbls(filename="w_lg_w_glbl_lbl_100ep.bin",
                                                                                   dict_=full_dict_results)
    mccs, mccs2 = get_pred_accs_sp_vs_nosp(life_grp, seqs, true_lbls, pred_lbls, v=False, return_mcc2=True,
                                           sp_type="SP")
    # LIPO is SEC/SPII
    mccs_lipo, mccs2_lipo = get_pred_accs_sp_vs_nosp(life_grp, seqs, true_lbls, pred_lbls, v=False, return_mcc2=True,
                                                     sp_type="LIPO")
    # TAT is TAT/SPI
    mccs_tat, mccs2_tat = get_pred_accs_sp_vs_nosp(life_grp, seqs, true_lbls, pred_lbls, v=False, return_mcc2=True,
                                                   sp_type="TAT")
    if "param_search_w_nl_nh_0.0_4096_1e-05_4_4" in run:
        v = False
    else:
        v = False
    all_recalls, all_precisions, _, _, _, f1_scores = \
        get_cs_acc(life_grp, seqs, true_lbls, pred_lbls, v=v, only_cs_position=only_cs_position, sp_type="SP", sptype_preds=full_sptype_dict)
    all_recalls_lipo, all_precisions_lipo, _, _, _, f1_scores_lipo = \
        get_cs_acc(life_grp, seqs, true_lbls, pred_lbls, v=v, only_cs_position=only_cs_position, sp_type="LIPO", sptype_preds=full_sptype_dict )
    all_recalls_tat, all_precisions_tat, _, _, _, f1_scores_tat = \
        get_cs_acc(life_grp, seqs, true_lbls, pred_lbls, v=v, only_cs_position=only_cs_position, sp_type="TAT", sptype_preds=full_sptype_dict)
    if return_sptype_f1:
        return mccs, mccs2, mccs_lipo, mccs2_lipo, mccs_tat, mccs2_tat, all_recalls, all_precisions, all_recalls_lipo, \
               all_precisions_lipo, all_recalls_tat, all_precisions_tat, avg_epoch, f1_scores, f1_scores_lipo, f1_scores_tat, get_class_sp_accs(life_grp, seqs, true_lbls, pred_lbls)
    return mccs, mccs2, mccs_lipo, mccs2_lipo, mccs_tat, mccs2_tat, all_recalls, all_precisions, all_recalls_lipo, \
           all_precisions_lipo, all_recalls_tat, all_precisions_tat, avg_epoch, f1_scores, f1_scores_lipo, f1_scores_tat


def get_best_corresponding_eval_mcc(result_folder="results_param_s_2/", model="", metric="mcc"):
    tr_fold = [[0, 1], [1, 2], [0, 2]]
    all_best_mccs = []
    for t_f in tr_fold:
        with open(result_folder + model + "_{}_{}.log".format(t_f[0], t_f[1])) as f:
            lines = f.readlines()
        ep2mcc = {}
        best_mcc = -1
        for l in lines:
            if best_mcc != -1:
                continue
            elif "VALIDATION" in l and metric == "mcc":
                if "mcc" in l:
                    ep, mccs = l.split(":")[2], l.split(":")[4]
                    ep = int(ep.split("epoch")[-1].replace(" ", ""))
                    mccs = mccs.replace(" ", "").split(",")
                    mccs = np.mean([float(mcc) for mcc in mccs])
                    ep2mcc[ep] = mccs
            elif "train/validation loss" in l and metric == "loss":

                ep, mccs = l.split(":")[2], l.split(":")[3]
                ep = int(ep.split("epoch")[-1].split(" ")[1])
                if "," in mccs:
                    mccs = float(mccs.replace(" ", "").split(",")[0].split("/")[1])
                    ep2mcc[ep] = mccs / 2
                else:
                    mccs = float(mccs.replace(" ", "").split("/")[1])
                    ep2mcc[ep] = mccs
            elif "TEST" in l and "epoch" in l and "mcc" in l:
                best_ep = int(l.split(":")[2].split("epoch")[-1].replace(" ", ""))
                avg_last_5 = []
                for i in range(5):
                    best_mcc = ep2mcc[best_ep - i]
                    avg_last_5.append(best_mcc)
                best_mcc = np.mean(avg_last_5)
        all_best_mccs.append(best_mcc)
    return np.mean(all_best_mccs)


def get_mean_results_for_mulitple_runs(mdlind2mdlparams, mdl2results, plot_type="prec-rec", tol=1):
    avg_mcc, avg_mcc2, avg_mcc_lipo, avg_mcc2_lipo, avg_mccs_tat, avg_mccs2_tat, avg_prec, avg_recall, avg_prec_lipo, \
    avg_recall_lipo, avg_prec_tat, avg_recall_tat, no_of_mdls = {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}
    for ind, results in mdl2results.items():
        mccs, mccs2, mccs_lipo, mccs2_lipo, mccs_tat, mccs2_tat, all_recalls, all_precisions, \
        all_recalls_lipo, all_precisions_lipo, all_recalls_tat, all_precisions_tat, _ = results
        mdl = mdlind2mdlparams[ind].split("run_no")[0]
        if "patience_30" in mdl:
            mdl = "patience_30"
        else:
            mdl = "patience_60"
        if mdl in no_of_mdls:
            no_of_mdls[mdl] += 1
            avg_mcc[mdl].append(np.array(mccs))
            avg_recall[mdl].append(np.array(all_recalls))
            avg_prec[mdl].append(np.array(all_precisions))
            avg_mcc2[mdl].append(np.array(mccs2))
            avg_mcc_lipo[mdl].append(np.array(mccs_lipo))
            avg_mcc2_lipo[mdl].append(np.array(mccs2_lipo))
            avg_mccs_tat[mdl].append(np.array(avg_mccs_tat))
            avg_mccs2_tat[mdl].append(np.array(avg_mccs2_tat))
            avg_recall_lipo[mdl].append(np.array(all_recalls_lipo))
            avg_prec_lipo[mdl].append(np.array(all_precisions_lipo))
            avg_recall_tat[mdl].append(np.array(all_recalls_tat))
            avg_prec_tat[mdl].append(np.array(all_precisions_tat))
        else:
            no_of_mdls[mdl] = 1
            avg_mcc[mdl] = [np.array(mccs)]
            avg_recall[mdl] = [np.array(all_recalls)]
            avg_prec[mdl] = [np.array(all_precisions)]
            avg_mcc2[mdl] = [np.array(mccs2)]
            avg_mcc_lipo[mdl] = [np.array(mccs_lipo)]
            avg_mcc2_lipo[mdl] = [np.array(mccs2_lipo)]
            avg_mccs_tat[mdl] = [np.array(avg_mccs_tat)]
            avg_mccs2_tat[mdl] = [np.array(avg_mccs2_tat)]
            avg_recall_lipo[mdl] = [np.array(all_recalls_lipo)]
            avg_prec_lipo[mdl] = [np.array(all_precisions_lipo)]
            avg_prec_tat[mdl] = [np.array(all_precisions_tat)]
            avg_recall_tat[mdl] = [np.array(all_recalls_tat)]
    fig, axs = plt.subplots(2, 3, figsize=(12, 8)) if plot_type == "mcc" else plt.subplots(2, 4, figsize=(12, 8))
    plt.subplots_adjust(right=0.7)
    colors = ['red', 'green', 'orange', 'blue', 'brown', 'black']

    models = list(avg_mcc.keys())
    mdl2colors = {models[i]: colors[i] for i in range(len(models))}

    print(set(models))
    # TODO: Configure this for model names (usually full names are quite long and ugly)
    mdl2mdlnames = {}
    for mdl in models:
        if "patience_30" in mdl:
            mdl2mdlnames[mdl] = "patience 30"
        else:
            mdl2mdlnames[mdl] = "patience 60"
    # for mdl in models:
    #     if "lr_sched_searchlrsched_step_wrmpLrSched_0_" in mdl:
    #         mdl2mdlnames[mdl] = "step, 0 wrmp"
    #
    #     if "lr_sched_searchlrsched_expo_wrmpLrSched_10_" in mdl:
    #         mdl2mdlnames[mdl] = "expo, 10 wrmp"
    #
    #     if "lr_sched_searchlrsched_expo_wrmpLrSched_0_" in mdl:
    #         mdl2mdlnames[mdl] = "expo, 0 wrmp"
    #
    #     if "lr_sched_searchlrsched_step_wrmpLrSched_10_" in mdl:
    #         mdl2mdlnames[mdl] = "step, 10 wrmp"
    #
    #     if "test_beam_search" in mdl:
    #         mdl2mdlnames[mdl] = "no sched"
    # FOR GLBL LBL
    # for mdl in models:
    #     if "glbl_lbl_search_use_glbl_lbls_version_1_weight_1_" in mdl:
    #         mdl2mdlnames[mdl] = "version 1 weight 1"
    #     if "glbl_lbl_search_use_glbl_lbls_version_2_weight_1_" in mdl:
    #         mdl2mdlnames[mdl] = "version 2 weight 1"
    #     if "glbl_lbl_search_use_glbl_lbls_version_2_weight_0.1_" in mdl:
    #         mdl2mdlnames[mdl] = "version 2 weight 0.1"
    #     if "glbl_lbl_search_use_glbl_lbls_version_1_weight_0.1_" in mdl:
    #         mdl2mdlnames[mdl] = "version 1 weight 0.1"
    #     if "test_beam_search" in mdl:
    #         mdl2mdlnames[mdl] = "no glbl labels"
    plot_lgs = ['NEGATIVE', 'POSITIVE', 'ARCHAEA'] if plot_type == "mcc" else ['EUKARYA', 'NEGATIVE', 'POSITIVE',
                                                                               'ARCHAEA']
    for lg_ind, lg in enumerate(plot_lgs):
        if plot_type == "mcc":
            axs[0, 0].set_ylabel("MCC")
            axs[1, 0].set_ylabel("MCC2")
        else:
            axs[0, 0].set_ylabel("Recall")
            axs[1, 0].set_ylabel("Precision")
        for mdl in avg_mccs_tat.keys():
            x = np.linspace(0, 1, 1000)
            if plot_type == "mcc":
                kde = stats.gaussian_kde([avg_mcc[mdl][i][lg_ind + 1] for i in range(no_of_mdls[mdl])])
            else:
                kde = stats.gaussian_kde([avg_recall[mdl][i][lg_ind * 4 + tol] for i in range(no_of_mdls[mdl])])

            if lg_ind == 0:
                axs[0, lg_ind].plot(x, kde(x), color=mdl2colors[mdl])  # , label="{}".format(mdl2mdlnames[mdl]))
            else:
                axs[0, lg_ind].plot(x, kde(x), color=mdl2colors[
                    mdl])  # , label="Eukaryote {} param search".format(mdl2mdlnames[mdl]))
            axs[0, lg_ind].set_title(lg + " SEC/SPI")
        for mdl in avg_mccs_tat.keys():
            x = np.linspace(0, 1, 1000)
            if plot_type == "mcc":
                kde = stats.gaussian_kde([avg_mcc2[mdl][i][lg_ind + 1] for i in range(no_of_mdls[mdl])])
            else:
                kde = stats.gaussian_kde([avg_prec[mdl][i][lg_ind * 4 + tol] for i in range(no_of_mdls[mdl])])
            axs[1, lg_ind].plot(x, kde(x),
                                color=mdl2colors[mdl])  # , label="Eukaryote {} param search".format(mdl2mdlnames[mdl]))
            if lg_ind == len(plot_lgs) - 1:
                axs[1, lg_ind].plot(x, kde(x), color=mdl2colors[
                    mdl], label="{}".format(mdl2mdlnames[mdl]))

    plot_lgs = ['NEGATIVE', 'POSITIVE', 'ARCHAEA']
    plt.legend(loc=(1.04, 1))
    plt.show()

    fig, axs = plt.subplots(2, 3, figsize=(12, 8))
    plt.subplots_adjust(right=0.7)
    for lg_ind, lg in enumerate(['NEGATIVE', 'POSITIVE', 'ARCHAEA']):
        if plot_type == "mcc":
            axs[0, 0].set_ylabel("MCC")
            axs[1, 0].set_ylabel("MCC2")
        else:
            axs[0, 0].set_ylabel("Recall")
            axs[1, 0].set_ylabel("Precision")
        for mdl in avg_mccs_tat.keys():
            x = np.linspace(0, 1, 1000)
            if plot_type == "mcc":
                kde = stats.gaussian_kde([avg_mcc_lipo[mdl][i][lg_ind] for i in range(no_of_mdls[mdl])])
            else:
                kde = stats.gaussian_kde([avg_recall_lipo[mdl][i][lg_ind * 4 + tol] for i in range(no_of_mdls[mdl])])
            if lg_ind == 0:
                axs[0, lg_ind].plot(x, kde(x), color=mdl2colors[mdl])  # , label="{}".format(mdl2mdlnames[mdl]))
            else:
                axs[0, lg_ind].plot(x, kde(x), color=mdl2colors[
                    mdl])  # , label="Eukaryote {} param search".format(mdl2mdlnames[mdl]))
            axs[0, lg_ind].set_title(lg + " SEC/SPII")
        for mdl in avg_mccs_tat.keys():
            x = np.linspace(0, 1, 1000)
            if plot_type == "mcc":
                kde = stats.gaussian_kde([avg_mcc2_lipo[mdl][i][lg_ind] for i in range(no_of_mdls[mdl])])
            else:
                kde = stats.gaussian_kde([avg_prec_lipo[mdl][i][lg_ind * 4 + tol] for i in range(no_of_mdls[mdl])])
            axs[1, lg_ind].plot(x, kde(x),
                                color=mdl2colors[mdl])  # , label="Eukaryote {} param search".format(mdl2mdlnames[mdl]))
            if lg_ind == 2:
                axs[1, lg_ind].plot(x, kde(x), color=mdl2colors[
                    mdl], label="{}".format(mdl2mdlnames[mdl]))

    plt.legend(loc=(1.04, 1))
    plt.show()

    fig, axs = plt.subplots(2, 3, figsize=(12, 8))
    plt.subplots_adjust(right=0.7)
    for lg_ind, lg in enumerate(['NEGATIVE', 'POSITIVE', 'ARCHAEA']):
        if plot_type == "mcc":
            axs[0, 0].set_ylabel("MCC")
            axs[1, 0].set_ylabel("MCC2")
        else:
            axs[0, 0].set_ylabel("Recall")
            axs[1, 0].set_ylabel("Precision")
        for mdl in avg_mccs_tat.keys():
            x = np.linspace(0, 1, 1000)
            if plot_type == "mcc":
                kde = stats.gaussian_kde([avg_mccs_tat[mdl][i][lg_ind] for i in range(no_of_mdls[mdl])])
            else:
                kde = stats.gaussian_kde([avg_recall_tat[mdl][i][lg_ind * 4 + tol] for i in range(no_of_mdls[mdl])])
            if lg_ind == 0:
                axs[0, lg_ind].plot(x, kde(x), color=mdl2colors[mdl])  # , label="{}".format(mdl2mdlnames[mdl]))
            else:
                axs[0, lg_ind].plot(x, kde(x), color=mdl2colors[
                    mdl])  # , label="Eukaryote {} param search".format(mdl2mdlnames[mdl]))
            axs[0, lg_ind].set_title(lg + " TAT/SPI")
        for mdl in avg_mccs_tat.keys():
            x = np.linspace(0, 1, 1000)
            if plot_type == "mcc":
                kde = stats.gaussian_kde([avg_mccs2_tat[mdl][i][lg_ind] for i in range(no_of_mdls[mdl])])
            else:
                kde = stats.gaussian_kde([avg_prec_tat[mdl][i][lg_ind * 4 + tol] for i in range(no_of_mdls[mdl])])
            axs[1, lg_ind].plot(x, kde(x),
                                color=mdl2colors[mdl])  # , label="Eukaryote {} param search".format(mdl2mdlnames[mdl]))
            if lg_ind == 2:
                axs[1, lg_ind].plot(x, kde(x), color=mdl2colors[
                    mdl], label="{}".format(mdl2mdlnames[mdl]))

    plt.legend(loc=(1.04, 1))
    plt.show()
    if plot_type == "mcc":
        fig, axs = plt.subplots(1, 1, figsize=(4, 8))
        plt.subplots_adjust(right=0.7)
        for lg_ind, lg in enumerate(['EUKARYOTE']):
            axs[0, 0].set_ylabel("MCC")
            for mdl in avg_mccs_tat.keys():
                x = np.linspace(0, 1, 1000)
                kde = stats.gaussian_kde([avg_mcc[mdl][i][lg_ind + 1] for i in range(no_of_mdls[mdl])])
                axs[0, lg_ind].plot(x, kde(x), color=mdl2colors[mdl], label="{}".format(mdl2mdlnames[mdl]))
                axs[0, lg_ind].set_title(lg + " SEC/SPI")
        plt.legend(loc=(1.04, 1))
        plt.show()


def get_f1_scores(rec, prec):
    return [2 * rec[i] * prec[i] / (rec[i] + prec[i]) if rec[i] + prec[i] != 0 else 0 for i in range(len(rec))]


def extract_all_param_results(result_folder="results_param_s_2/", only_cs_position=False, compare_mdl_plots=False,
                              remove_test_seqs=False, benchmark=True):
    sp6_recalls_sp1 = [0.747, 0.774, 0.808, 0.829, 0.639, 0.672, 0.689, 0.721, 0.800, 0.800, 0.800, 0.800, 0.500, 0.556,
                       0.556, 0.583]
    sp6_recalls_sp2 = [0.852, 0.852, 0.856, 0.864, 0.875, 0.883, 0.883, 0.883, 0.778, 0.778, 0.778, 0.778]
    sp6_recalls_tat = [0.706, 0.765, 0.784, 0.804, 0.556, 0.556, 0.667, 0.667, 0.333, 0.444, 0.444, 0.444]
    sp6_precs_sp1 = [0.661, 0.685, 0.715, 0.733, 0.534, 0.562, 0.575, 0.603, 0.632, 0.632, 0.632, 0.632, 0.643, 0.714,
                     0.714, 0.75]
    sp6_precs_sp2 = [0.913, 0.913, 0.917, 0.925, 0.929, 0.938, 0.938, 0.938, 0.583, 0.583, 0.583, 0.583]
    sp6_precs_tat = [0.679, 0.736, 0.755, 0.774, 0.714, 0.714, 0.857, 0.857, 0.375, 0.5, 0.5, 0.5]
    sp6_f1_sp1 = get_f1_scores(sp6_recalls_sp1, sp6_precs_sp1)
    sp6_f1_sp2 = get_f1_scores(sp6_recalls_sp2, sp6_precs_sp2)
    sp6_f1_tat = get_f1_scores(sp6_recalls_tat, sp6_precs_tat)

    if benchmark:
        no_of_seqs_sp1 = list(np.array([146, 61, 15, 36]).repeat(4))
        no_of_seqs_sp2 = list(np.array([257, 120, 9]).repeat(4))
        no_of_seqs_tat = list(np.array([51 ,18, 9]).repeat(4))
        no_of_tested_sp_seqs = sum([146, 61, 15, 36]) + sum([257, 120, 9]) + sum([51 ,18, 9])
    else:
        no_of_seqs_sp1 = list(np.array([2040, 44, 142, 356]).repeat(4))
        no_of_seqs_sp2 = list(np.array([1087, 516, 12]).repeat(4))
        no_of_seqs_tat = list(np.array([313 ,39, 13]).repeat(4))
        no_of_tested_sp_seqs = sum([2040, 44, 142, 356]) + sum([1087, 516, 12]) + sum([313 ,39, 13])
    sp6_summarized = np.sum((np.array(sp6_f1_sp1) * np.array(no_of_seqs_sp1))) / no_of_tested_sp_seqs + \
                        np.sum((np.array(sp6_f1_sp2) * np.array(no_of_seqs_sp2))) / no_of_tested_sp_seqs + \
                        np.sum((np.array(sp6_f1_tat) * np.array(no_of_seqs_tat))) / no_of_tested_sp_seqs
    sp6_recalls_sp1 = [str(round(sp6_r_sp1, 2)) for sp6_r_sp1 in sp6_recalls_sp1]
    sp6_recalls_sp2 = [str(round(sp6_r_sp2, 2)) for sp6_r_sp2 in sp6_recalls_sp2]
    sp6_recalls_tat = [str(round(sp6_r_tat, 2)) for sp6_r_tat in sp6_recalls_tat]
    sp6_precs_sp1 = [str(round(sp6_prec_sp1, 2)) for sp6_prec_sp1 in sp6_precs_sp1]
    sp6_precs_sp2 = [str(round(sp6_p_sp2, 2)) for sp6_p_sp2 in sp6_precs_sp2]
    sp6_precs_tat = [str(round(sp6_p_tat, 2)) for sp6_p_tat in sp6_precs_tat]
    sp6_f1_sp1 = [str(round(sp6_f1_sp1_, 2)) for sp6_f1_sp1_ in sp6_f1_sp1]
    sp6_f1_sp2 = [str(round(sp6_f1_sp2_, 2)) for sp6_f1_sp2_ in sp6_f1_sp2]
    sp6_f1_tat = [str(round(sp6_f1_tat_, 2)) for sp6_f1_tat_ in sp6_f1_tat]
    files = os.listdir(result_folder)
    unique_params = set()
    for f in files:
        if "log" in f:
            # check if all 3 folds have finished
            dont_add = False
            for tr_f in [[0, 1], [1, 2], [0, 2]]:
                if "_".join(f.split("_")[:-2]) + "_{}_{}_best.bin".format(tr_f[0], tr_f[1]) not in files:
                    dont_add = True
            if not dont_add:
                unique_params.add("_".join(f.split("_")[:-2]))
    mdl2results = {}
    mdl2summarized_results = {}
    mdlind2mdlparams = {}
    # order results by the eukaryote mcc
    eukaryote_mcc = []
    for ind, u_p in enumerate(unique_params):
        mccs, mccs2, mccs_lipo, mccs2_lipo, mccs_tat, mccs2_tat, \
        all_recalls, all_precisions, all_recalls_lipo, all_precisions_lipo, \
        all_recalls_tat, all_precisions_tat, avg_epoch, f1_scores, f1_scores_lipo, f1_scores_tat, f1_scores_sptype \
            = extract_mean_test_results(run=u_p, result_folder=result_folder,
                                        only_cs_position=only_cs_position,
                                        remove_test_seqs=remove_test_seqs, return_sptype_f1=True, benchmark=benchmark)
        all_recalls_lipo, all_precisions_lipo, \
        all_recalls_tat, all_precisions_tat, = list(np.reshape(np.array(all_recalls_lipo), -1)), list(
            np.reshape(np.array(all_precisions_lipo), -1)), \
                                               list(np.reshape(np.array(all_recalls_tat), -1)), list(
            np.reshape(np.array(all_precisions_tat), -1))
        mdl2results[ind] = (
        mccs, mccs2, mccs_lipo, mccs2_lipo, mccs_tat, mccs2_tat, list(np.reshape(np.array(all_recalls), -1)),
        list(np.reshape(np.array(all_precisions), -1)), all_recalls_lipo, all_precisions_lipo,
        all_recalls_tat, all_precisions_tat, f1_scores, f1_scores_lipo, f1_scores_tat, f1_scores_sptype, avg_epoch)
        mdl2summarized_results[ind] = np.sum((np.array(f1_scores).reshape(-1) * np.array(no_of_seqs_sp1)))/no_of_tested_sp_seqs + \
                                      np.sum((np.array(f1_scores_lipo).reshape(-1) * np.array(no_of_seqs_sp2)))/no_of_tested_sp_seqs + \
                                      np.sum((np.array(f1_scores_tat).reshape(-1) * np.array(no_of_seqs_tat)))/no_of_tested_sp_seqs
        mdlind2mdlparams[ind] = u_p
        eukaryote_mcc.append(get_best_corresponding_eval_mcc(result_folder, u_p))
    if compare_mdl_plots:
        get_mean_results_for_mulitple_runs(mdlind2mdlparams, mdl2results)
    best_to_worst_mdls = np.argsort(eukaryote_mcc)[::-1]
    for mdl_ind in best_to_worst_mdls:
        params = ""
        mdl_params = mdlind2mdlparams[mdl_ind]
        if "use_glbl_lbls" in mdl_params:
            params += "wGlbl"
        else:
            params += "nGlbl"
        # patience_ind = mdl_params.find("patience_") + len("patience_")
        # patience = mdl_params[patience_ind:patience_ind+2]
        # params += "_{}".format(patience)
        if "nlayers" in mdl_params:
            nlayers = mdl_params[mdl_params.find("nlayers") + len("nlayers"):].split("_")[1]
            params += "_{}".format(nlayers)
        if "nhead" in mdl_params:
            nhead = mdl_params[mdl_params.find("nhead") + len("nhead"):].split("_")[1]
            params += "_{}".format(nhead)
        if "lrsched" in mdl_params:
            lr_sched = mdl_params[mdl_params.find("lrsched") + len("lrsched"):].split("_")[1]
            params += "_{}".format(lr_sched)
        if "dos" in mdl_params:
            dos = mdl_params[mdl_params.find("dos"):].split("_")[1]
            params += "_{}".format(dos)
        mdlind2mdlparams[mdl_ind] = params

    print("\n\nMCC SEC/SPI TABLE\n\n")
    for mdl_ind in best_to_worst_mdls:
        mdl_params = " & ".join(mdlind2mdlparams[mdl_ind].split("_"))
        print(mdl_params, " & ", " & ".join([str(round(mcc, 3)) for mcc in mdl2results[mdl_ind][0]]), "&",
              " & ".join([str(round(mcc, 3)) for mcc in mdl2results[mdl_ind][1][1:]]), " & ",
              round(mdl2results[mdl_ind][-1], 3), "\\\\ \\hline")

    print("\n\nF1 table SEC/SPI\n\n")
    no_of_params = len(mdlind2mdlparams[best_to_worst_mdls[0]].split("_"))
    print(" SP6 ", " & " * no_of_params, " & ".join(sp6_f1_sp1), " & \\\\ \\hline")
    for mdl_ind in best_to_worst_mdls:
        print("total f1 for {}: {} compared to sp6: {}".format(mdl_ind, mdl2summarized_results[mdl_ind]/4, sp6_summarized/4))
        print(" & ".join(mdlind2mdlparams[mdl_ind].split("_")), " & ",
              " & ".join([str(round(rec, 3)) for rec in np.concatenate(mdl2results[mdl_ind][-5])]), " & ",
              round(mdl2results[mdl_ind][-1], 3), "\\\\ \\hline")

    print("\n\nRecall table SEC/SPI\n\n")
    print(" SP6 ", " & " * no_of_params, " & ".join(sp6_recalls_sp1), " & \\\\ \\hline")
    for mdl_ind in best_to_worst_mdls:
        print(" & ".join(mdlind2mdlparams[mdl_ind].split("_")), " & ",
              " & ".join([str(round(rec, 3)) for rec in mdl2results[mdl_ind][6]]), " & ",
              round(mdl2results[mdl_ind][-1], 3), "\\\\ \\hline")

    print("\n\nPrec table SEC/SPI\n\n")
    print(" SP6 ", " & " * no_of_params, " & ".join(sp6_precs_sp1), " & \\\\ \\hline")
    for mdl_ind in best_to_worst_mdls:
        print(" & ".join(mdlind2mdlparams[mdl_ind].split("_")), " & ",
              " & ".join([str(round(rec, 3)) for rec in mdl2results[mdl_ind][7]]), "&",
              round(mdl2results[mdl_ind][-1], 3), "\\\\ \\hline")

    print("\n\nF1 table SEC/SPII \n\n")
    print(" SP6 ", " & " * no_of_params, " & ".join(sp6_f1_sp2), " & \\\\ \\hline")
    for mdl_ind in best_to_worst_mdls:
        print(" & ".join(mdlind2mdlparams[mdl_ind].split("_")), " & ",
              " & ".join([str(round(rec, 3)) for rec in np.concatenate(mdl2results[mdl_ind][-4])]), "&",
              round(mdl2results[mdl_ind][-1], 3), "\\\\ \\hline")

    print("\n\nRecall table SEC/SPII \n\n")
    print(" SP6 ", " & " * no_of_params, " & ".join(sp6_recalls_sp2), " & \\\\ \\hline")
    for mdl_ind in best_to_worst_mdls:
        print(" & ".join(mdlind2mdlparams[mdl_ind].split("_")), " & ",
              " & ".join([str(round(rec, 3)) for rec in mdl2results[mdl_ind][8]]), "&",
              round(mdl2results[mdl_ind][-1], 3), "\\\\ \\hline")

    print("\n\nPrec table SEC/SPII \n\n")
    print(" SP6 ", " & " * no_of_params, " & ".join(sp6_precs_sp2), " & \\\\ \\hline")
    for mdl_ind in best_to_worst_mdls:
        print(" & ".join(mdlind2mdlparams[mdl_ind].split("_")), " & ",
              " & ".join([str(round(rec, 3)) for rec in mdl2results[mdl_ind][9]]), "&",
              round(mdl2results[mdl_ind][-1], 3), "\\\\ \\hline")

    print("\n\nF1 table TAT/SPI \n\n")
    print(" SP6 ", " & " * no_of_params, " & ".join(sp6_f1_tat), " & \\\\ \\hline")
    for mdl_ind in best_to_worst_mdls:
        print(" & ".join(mdlind2mdlparams[mdl_ind].split("_")), " & ",
              " & ".join([str(round(rec, 3)) for rec in np.concatenate(mdl2results[mdl_ind][-3])]), "&",
              round(mdl2results[mdl_ind][-1], 3), "\\\\ \\hline")

    print("\n\nRecall table TAT/SPI \n\n")
    print(" SP6 ", " & " * no_of_params, " & ".join(sp6_recalls_tat), " & \\\\ \\hline")
    for mdl_ind in best_to_worst_mdls:
        print(" & ".join(mdlind2mdlparams[mdl_ind].split("_")), " & ",
              " & ".join([str(round(rec, 3)) for rec in mdl2results[mdl_ind][10]]), "&",
              round(mdl2results[mdl_ind][-1], 3), "\\\\ \\hline")

    print("\n\nPrec table TAT/SPI \n\n")
    print(" SP6 ", " & " * no_of_params, " & ".join(sp6_precs_tat), " & \\\\ \\hline")
    for mdl_ind in best_to_worst_mdls:
        print(" & ".join(mdlind2mdlparams[mdl_ind].split("_")), " & ",
              " & ".join([str(round(rec, 3)) for rec in mdl2results[mdl_ind][11]]), "&",
              round(mdl2results[mdl_ind][-1], 3), "\\\\ \\hline")

    print("\n\nMCC SEC/SPII TABLE\n\n")
    for mdl_ind in best_to_worst_mdls:
        print(" & ".join(mdlind2mdlparams[mdl_ind].split("_")), " & ",
              " & ".join([str(round(mcc, 3)) for mcc in mdl2results[mdl_ind][2]]), "&",
              " & ".join([str(round(mcc, 3)) for mcc in mdl2results[mdl_ind][3]]), "&",
              round(mdl2results[mdl_ind][-1], 3), "\\\\ \\hline")

    print("\n\nMCC TAT/SPI TABLE\n\n")
    for mdl_ind in best_to_worst_mdls:
        print(" & ".join(mdlind2mdlparams[mdl_ind].split("_")), " & ",
              " & ".join([str(round(mcc, 3)) for mcc in mdl2results[mdl_ind][4]]), "&",
              " & ".join([str(round(mcc, 3)) for mcc in mdl2results[mdl_ind][5]]), "&",
              round(mdl2results[mdl_ind][-1], 3), "\\\\ \\hline")

    print("\n\nSP-type preds F1\n\n")
    for mdl_ind in best_to_worst_mdls:
        print(" & ".join(mdlind2mdlparams[mdl_ind].split("_")), " & ",
              " & ".join([str(round(mcc, 3)) for mcc in mdl2results[mdl_ind][-2]]), "&",
              round(mdl2results[mdl_ind][-1], 3), "\\\\ \\hline")

    return mdl2results


def sanity_checks(run="param_search_0_2048_0.0001_", folder="results/"):
    # S = signal_peptide; T = Tat/SPI or Tat/SPII SP; L = Sec/SPII SP; P = SEC/SPIII SP; I = cytoplasm; M = transmembrane; O = extracellular;

    def get_last_contiguous_index(seq, signal_peptide):
        ind = 0
        while seq[ind] == signal_peptide and ind < len(seq) - 1:
            ind += 1
        return ind - 1

    def check_contiguous_sp(lbl_seqs):
        for l in lbl_seqs:
            signal_peptide = None
            l = l.replace("ES", "")
            if "S" in l:
                signal_peptide = "S"
            elif "T" in l:
                signal_peptide = "T"
            elif "L" in l:
                signal_peptide = "L"
            elif "P" in l:
                signal_peptide = "P"
            if signal_peptide is not None:

                if l.rfind(signal_peptide) != get_last_contiguous_index(l, signal_peptide):
                    print(l, l.rfind(signal_peptide), get_last_contiguous_index(l, signal_peptide), signal_peptide)

    for tr_fold in [[0, 1], [1, 2], [0, 2]]:
        labels = pickle.load(open(folder + run + "{}_{}.bin".format(tr_fold[0], tr_fold[1]), "rb")).values()
        check_contiguous_sp(labels)


def extract_all_mdl_results(mdl2results):
    euk_mcc, neg_mcc, pos_mcc, arch_mcc = [], [], [], []
    euk_rec, neg_rec, pos_rec, arch_rec = [[], [], [], []], [[], [], [], []], [[], [], [], []], [[], [], [], []]
    euk_prec, neg_prec, pos_prec, arch_prec = [[], [], [], []], [[], [], [], []], [[], [], [], []], [[], [], [], []]
    for _, (mccs, recalls, precisions, epochs) in mdl2results.items():
        euk_mcc.append(mccs[0])
        neg_mcc.append(mccs[1])
        pos_mcc.append(mccs[2])
        arch_mcc.append(mccs[3])
        euk_rec[0].append(recalls[0])
        euk_rec[1].append(recalls[1])
        euk_rec[2].append(recalls[2])
        euk_rec[3].append(recalls[3])
        neg_rec[0].append(recalls[4])
        neg_rec[1].append(recalls[5])
        neg_rec[2].append(recalls[6])
        neg_rec[3].append(recalls[7])
        pos_rec[0].append(recalls[8])
        pos_rec[1].append(recalls[9])
        pos_rec[2].append(recalls[10])
        pos_rec[3].append(recalls[11])
        arch_rec[0].append(recalls[12])
        arch_rec[1].append(recalls[13])
        arch_rec[2].append(recalls[14])
        arch_rec[3].append(recalls[15])

        euk_prec[0].append(precisions[0])
        euk_prec[1].append(precisions[1])
        euk_prec[2].append(precisions[2])
        euk_prec[3].append(precisions[3])
        neg_prec[0].append(precisions[4])
        neg_prec[1].append(precisions[5])
        neg_prec[2].append(precisions[6])
        neg_prec[3].append(precisions[7])
        pos_prec[0].append(precisions[8])
        pos_prec[1].append(precisions[9])
        pos_prec[2].append(precisions[10])
        pos_prec[3].append(precisions[11])
        arch_prec[0].append(precisions[12])
        arch_prec[1].append(precisions[13])
        arch_prec[2].append(precisions[14])
        arch_prec[3].append(precisions[15])
    return euk_mcc, neg_mcc, pos_mcc, arch_mcc, euk_rec, neg_rec, pos_rec, arch_rec, euk_prec, neg_prec, pos_prec, arch_prec


def visualize_training_variance(mdl2results, mdl2results_hps=None):
    def plot_4_figs(measures, sp6_measure, hp_s_measures=None, name="", plot_hps=False):
        euk, neg, pos, arch = measures
        if plot_hps:
            euk_hps, neg_hps, pos_hps, arch_hps = hp_s_measures

        fig, axs = plt.subplots(2, 2, figsize=(12, 8))
        fig.suptitle(name)
        x = np.linspace(0, 1, 1000)
        kde = stats.gaussian_kde(euk)
        # axs[0, 0].plot(x, kde(x), color = "blue", label="Eukaryote {}".format(name))
        axs[0, 0].hist(euk, color="blue", bins=10, label="Eukaryote {}".format(name))
        if plot_hps:
            kde = stats.gaussian_kde(euk_hps)
            axs[0, 0].hist(euk_hps, alpha=0.5, color="red", bins=10, label="Eukaryote {} param search".format(name))
            # axs[0, 0].plot(x, kde(x), color = "red", label="Eukaryote {} param search".format(name))
        axs[0, 0].set_ylabel("No of models")
        axs[0, 0].set_xlim(0, 1)
        axs[0, 0].plot([sp6_measure[0], sp6_measure[0]], [0, 5], 'r--', label="SP6 result")
        axs[0, 0].legend()

        kde = stats.gaussian_kde(neg)
        axs[0, 1].hist(neg, bins=10, color="blue", label="Negative {}".format(name))
        # axs[0, 1].plot(x, kde(x), color = "blue", label="Negative {}".format(name))
        if plot_hps:
            kde = stats.gaussian_kde(neg_hps)
            axs[0, 1].hist(neg_hps, alpha=0.5, bins=10, color="red", label="Negative {} param search".format(name))
            # axs[0, 1].plot(x, kde(x), color = "red", label="Negative {} param search".format(name))
        axs[0, 1].set_xlim(0, 1)
        axs[0, 1].plot([sp6_measure[1], sp6_measure[1]], [0, 5], 'r--', label="SP6 result")

        axs[0, 1].legend()

        # axs[1, 0].hist(pos,bins=10,color = "blue", label="Positive {}".format(name))
        kde = stats.gaussian_kde(pos)
        axs[1, 0].hist(pos, bins=10, color="blue", label="Positive {}".format(name))
        # axs[1, 0].plot(x, kde(x), color = "blue", label="Positive {}".format(name))

        if plot_hps:
            # kde = stats.gaussian_kde(pos_hps)
            axs[1, 0].hist(pos_hps, color="red", alpha=0.5, bins=10, label="Positive {} param search".format(name))
            axs[1, 0].plot(x, kde(x), color="red", label="Positive {} param search".format(name))

        axs[1, 0].set_xlim(0, 1)
        axs[1, 0].set_ylabel("No of models")
        axs[1, 0].plot([sp6_measure[2], sp6_measure[2]], [0, 5], 'r--', label="SP6 result")
        axs[1, 0].legend()
        axs[1, 0].set_xlabel(name.split(" ")[0])

        kde = stats.gaussian_kde(arch)
        axs[1, 1].hist(arch, bins=10, color="blue", label="Archaea {}".format(name))
        # axs[1, 1].plot(x, kde(x), color = "blue",label="Archaea {}".format(name))
        if plot_hps:
            kde = stats.gaussian_kde(arch_hps)
            axs[1, 1].hist(arch_hps, alpha=0.5, color="red", bins=10, label="Archaea {} param search".format(name))
            # axs[1, 1].plot(x, kde(x), color = "red", label="Archaea {} param search".format(name))
        axs[1, 1].set_xlim(0, 1)
        axs[1, 1].plot([sp6_measure[3], sp6_measure[3]], [0, 5], 'r--', label="SP6 result")

        axs[1, 1].legend()
        axs[1, 1].set_xlabel(name.split(" ")[0])
        plt.show()
        # plt.savefig("/home/alex/Desktop/sp6_ds_transformer_nmt_results/{}_{}.png".format(name, "mcc"))

    euk_mcc_sp6, neg_mcc_sp6, pos_mcc_sp6, arch_mcc_sp6 = 0.868, 0.811, 0.878, 0.737
    euk_rec_sp6, neg_rec_sp6, pos_rec_sp6, arch_rec_sp6 = [0.747, 0.774, 0.808, 0.829], [0.639, 0.672, 0.689, 0.721], \
                                                          [0.800, 0.800, 0.800, 0.800], [0.500, 0.556, 0.556, 0.583]
    euk_prec_sp6, neg_prec_sp6, pos_prec_sp6, arch_prec_sp6 = [0.661, 0.685, 0.715, 0.733], [0.534, 0.562, 0.575,
                                                                                             0.603], \
                                                              [0.632, 0.632, 0.632, 0.632], [0.643, 0.714, 0.714, 0.75]
    euk_mcc, neg_mcc, pos_mcc, arch_mcc, euk_rec, neg_rec, \
    pos_rec, arch_rec, euk_prec, neg_prec, pos_prec, arch_prec = extract_all_mdl_results(mdl2results)
    if mdl2results_hps is not None:
        euk_hps_mcc, neg_hps_mcc, pos_hps_mcc, arch_hps_mcc, euk_hps_rec, neg_hps_rec, pos_hps_rec, arch_hps_rec, \
        euk_hps_prec, neg_hps_prec, pos_hps_prec, arch_hps_prec = extract_all_mdl_results(mdl2results_hps)
    else:
        euk_hps_mcc, neg_hps_mcc, pos_hps_mcc, arch_hps_mcc, euk_hps_rec, neg_hps_rec, pos_hps_rec, arch_hps_rec, \
        euk_hps_prec, neg_hps_prec, pos_hps_prec, arch_hps_prec = None, None, None, None, [None, None, None, None], \
                                                                  [None, None, None, None], [None, None, None, None], \
                                                                  [None, None, None, None], [None, None, None, None], \
                                                                  [None, None, None, None], [None, None, None, None], \
                                                                  [None, None, None, None]
    plot_hps = mdl2results_hps is not None
    plot_4_figs([euk_mcc, neg_mcc, pos_mcc, arch_mcc],
                [euk_mcc_sp6, neg_mcc_sp6, pos_mcc_sp6, arch_mcc_sp6],
                [euk_hps_mcc, neg_hps_mcc, pos_hps_mcc, arch_hps_mcc],
                name='mcc', plot_hps=plot_hps)
    for i in range(4):
        plot_4_figs([euk_rec[i], neg_rec[i], pos_rec[i], arch_rec[i]],
                    [euk_rec_sp6[i], neg_rec_sp6[i], pos_rec_sp6[i], arch_rec_sp6[i]],
                    [euk_hps_rec[i], neg_hps_rec[i], pos_hps_rec[i], arch_hps_rec[i]],
                    name='recall tol={}'.format(i), plot_hps=plot_hps)
        plot_4_figs([euk_prec[i], neg_prec[i], pos_prec[i], arch_prec[i]],
                    [euk_prec_sp6[i], neg_prec_sp6[i], pos_prec_sp6[i], arch_prec_sp6[i]],
                    [euk_hps_prec[i], neg_hps_prec[i], pos_hps_prec[i], arch_hps_prec[i]],
                    name='precision tol={}'.format(i), plot_hps=plot_hps)


def extract_calibration_probs_for_mdl(model="parameter_search_patience_60use_glbl_lbls_use_glbl_lbls_versio"
                                            "n_1_weight_0.1_lr_1e-05_nlayers_3_nhead_16_lrsched_none_trFlds_",
                                      folder='huge_param_search/patience_60/'):
    all_lg, all_seqs, all_tl, all_pred_lbls, sp2probs = [], [], [], [], {}
    for tr_f in [[0, 1], [0, 2], [1, 2]]:
        prob_file = "{}{}_{}_best_sp_probs.bin".format(model, tr_f[0], tr_f[1])
        preds_file = "{}{}_{}_best.bin".format(model, tr_f[0], tr_f[1])
        life_grp, seqs, true_lbls, pred_lbls = extract_seq_group_for_predicted_aa_lbls(filename=folder + preds_file)
        all_lg.extend(life_grp)
        all_seqs.extend(seqs)
        all_tl.extend(true_lbls)
        all_pred_lbls.extend(pred_lbls)
        sp2probs.update(pickle.load(open(folder + prob_file, "rb")))
    get_prob_calibration_and_plot("", all_lg, all_seqs, all_tl, all_pred_lbls, sp2probs=sp2probs)


def duplicate_Some_logs():
    from subprocess import call

    files = os.listdir("beam_test")
    for f in files:
        if "log" in f:
            file = f.replace(".bin", "_best.bin")
            cmd = ["cp", "beam_test/" + f, "beam_test/actual_beams/best_beam_" + file]
            call(cmd)
    exit(1)

def prep_sp1_sp2():

    file = "../sp_data/sp6_data/benchmark_set_sp5.fasta"
    file_new = "../sp_data/sp6_data/train_set.fasta"
    ids_benchmark_sp5 = []
    for seq_record in SeqIO.parse(file, "fasta"):
        ids_benchmark_sp5.append(seq_record.id.split("|")[0])
    seqs, ids = [], []
    lines = []
    for seq_record in SeqIO.parse(file_new, "fasta"):
        if seq_record.id.split("|")[0] in ids_benchmark_sp5 and "ARCHAEA" in seq_record.id:
            seqs.append(seq_record.seq[:len(seq_record.seq) // 2])
            ids.append(seq_record.id)
            lines.append(">"+ids[-1]+"\n")
            lines.append(str(seqs[-1])+"\n")
    for i in range(len(lines) // 50000 + 1) :
        with open("sp1_sp2_fastas/deepsig_arch.fasta".format(i), "wt") as f:
            f.writelines(lines[i * 50000:(i+1) * 50000])

def ask_uniprot():
    cID='P0AAK7'

    baseUrl="http://www.uniprot.org/uniprot/"
    currentUrl=baseUrl+cID+".fasta"
    response = r.post(currentUrl)
    cData=''.join(response.text)
    return int(cData.split("PE=")[1].split(" ")[0])

def correct_duplicates_training_data():
    sublbls=True
    file_new = "../sp_data/sp6_data/train_set.fasta"
    decided_ids = ['B3GZ85', 'B0R5Y3', 'Q0T616', 'Q7CI09', 'P33937', 'P63883', 'P33937', 'Q9P121', 'C1CTN0', 'Q8FAX0',
                   'P9WK51', 'Q5GZP1', 'P0AD45', 'P0DC88', 'Q8E6W4', 'Q5HMD1', 'Q2FWG4', 'Q5HLG6', 'Q8Y7A9', 'P65631',
                   'B1AIC4', 'Q2FZJ9', ' P0ABJ2', 'P0AD46', 'P0ABJ2', 'Q99V36', 'Q7A698', 'Q5HH23', 'Q6GI23', 'Q7A181',
                   'Q2YX14', 'Q6GAF2', 'P65628', 'P65629', 'P65630', 'Q5HEA9', 'P0DC86', 'Q2YUI9', 'Q5XDY9', 'Q2FF36',
                   'Q1R3H8', 'P0DC87', 'A5IUN6', 'A6QIT4', 'A7X4S6', 'Q6G7M0', 'Q1CHD5']
    #
    decided_ids_2_info = {}
    decided_str_2_info = {}
    processed_seqs = []
    for seq_record in SeqIO.parse(file_new, "fasta"):
        if str(seq_record.seq[: len(seq_record.seq) // 2]) in processed_seqs:
            if seq_record.id.split("|")[0] in decided_ids:
                decided_str_2_info[str(seq_record.seq[: len(seq_record.seq) // 2])] = (seq_record.id.split("|")[1],
                                                                                  seq_record.id.split("|")[2],
                                                                                  seq_record.id.split("|")[3],
                                                                                  str(seq_record.seq[len(seq_record.seq)//2:]))
        else:
            decided_str_2_info[str(seq_record.seq[: len(seq_record.seq) // 2])] = (seq_record.id.split("|")[1],
                                                                                  seq_record.id.split("|")[2],
                                                                                  seq_record.id.split("|")[3],
                                                                                  str(seq_record.seq[len(seq_record.seq)//2:]))
    # POSITIVE', 'TAT', '0', 'TTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO'
    # (emb, , 'IIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIII', 'EUKARYA', 'NO_SP')
    # sp6_partitioned_data_test_2.bin
    remove_count, remove_count2 = 0, 0
    total_count = 0
    seen_seqs = []
    removed_lbls = []
    for tr_f in [0, 1, 2]:
        for t_s in ["train", "test"]:
            new_seqs_2_info = {}
            seqs = pickle.load(open("../sp_data/sp6_partitioned_data_{}_{}.bin".format(t_s, tr_f), "rb")) \
                if not sublbls else pickle.load(open("../sp_data/sp6_partitioned_data_sublbls_{}_{}.bin".format(t_s, tr_f), "rb"))
            for k, info in seqs.items():
                total_count += 1
                if info[1] != decided_str_2_info[k][-1] or info[2] != decided_str_2_info[k][0] or  info[3] != decided_str_2_info[k][1] :
                    remove_count += 1
                    removed_lbls.append((info[1], decided_str_2_info[k][-1]))
                    newlbls = info[1] if decided_str_2_info[k][1] != "TATLIPO" or sublbls else info[1].replace("T", "W")
                    new_seqs_2_info[k] = (newlbls, decided_str_2_info[k][-1], decided_str_2_info[k][0], decided_str_2_info[k][1])
                elif k in seen_seqs:
                    removed_lbls.append((info[1], decided_str_2_info[k][-1]))
                    remove_count2+=1

                elif k not in seen_seqs:
                    seen_seqs.append(k)
                    newlbls = info[1].replace("T", "W") if info[-1] == "TATLIPO" and not sublbls else info[1]
                    new_seqs_2_info[k] = (info[0], newlbls, info[2], info[3])
            key = list(new_seqs_2_info.keys())[0]
            if sublbls:
                pickle.dump(new_seqs_2_info, open("../sp_data/sp6_partitioned_data_sublbls_{}_{}.bin".format(t_s, tr_f), "wb"))
            else:
                pickle.dump(new_seqs_2_info, open("../sp_data/sp6_partitioned_data_{}_{}.bin".format(t_s, tr_f), "wb"))

def count_seqs_lgs(seqs):
    file_new = "../sp_data/sp6_data/train_set.fasta"
    id2seq = {}
    id2lg = {}
    id2type = {}
    id2truelbls = {}
    ids_benchmark_sp5 = []
    seen_seqs = []
    count_seqs = {"EUKARYA":{"NO_SP":0, "SP":0}, "NEGATIVE":{"NO_SP":0, "SP":0, "TAT":0, "TATLIPO":0, "PILIN":0, "LIPO":0},
                  "POSITIVE":{"NO_SP":0, "SP":0, "TAT":0, "TATLIPO":0, "PILIN":0, "LIPO":0}, "ARCHAEA":{"NO_SP":0, "SP":0, "TAT":0, "TATLIPO":0, "PILIN":0, "LIPO":0}}
    for seq_record in SeqIO.parse(file_new, "fasta"):
        if str(seq_record.seq[:len(seq_record.seq) // 2]) in seqs and str(seq_record.seq[:len(seq_record.seq) // 2]) not in seen_seqs:
            seen_seqs.append(seq_record.seq[:len(seq_record.seq) // 2])
            sp_type = str(seq_record.id.split("|")[2])
            lg = str(seq_record.id.split("|")[1])
            count_seqs[lg][sp_type] +=1
    print(count_seqs)

def extract_id2seq_dict(file="train_set.fasta"):

    # for seq_record in SeqIO.parse(file_new, "fasta"):
    # id2seq[seq_record.id.split("|")[0]] = str(seq_record.seq[:len(seq_record.seq) // 2])
    # id2truelbls[seq_record.id.split("|")[0]] = str(seq_record.seq[len(seq_record.seq) // 2:])
    # id2lg[seq_record.id.split("|")[0]] = str(seq_record.id.split("|")[1])
    # id2type[seq_record.id.split("|")[0]] = str(seq_record.id.split("|")[2])
    decided_ids = ['B3GZ85', 'B0R5Y3', 'Q0T616', 'Q7CI09', 'P33937', 'P63883', 'P33937', 'Q9P121', 'C1CTN0', 'Q8FAX0',
                   'P9WK51', 'Q5GZP1', 'P0AD45', 'P0DC88', 'Q8E6W4', 'Q5HMD1', 'Q2FWG4', 'Q5HLG6', 'Q8Y7A9', 'P65631',
                   'B1AIC4', 'Q2FZJ9', ' P0ABJ2', 'P0AD46', 'P0ABJ2', 'Q99V36', 'Q7A698', 'Q5HH23', 'Q6GI23', 'Q7A181',
                   'Q2YX14', 'Q6GAF2', 'P65628', 'P65629', 'P65630', 'Q5HEA9', 'P0DC86', 'Q2YUI9', 'Q5XDY9', 'Q2FF36',
                   'Q1R3H8', 'P0DC87', 'A5IUN6', 'A6QIT4', 'A7X4S6', 'Q6G7M0', 'Q1CHD5']
    file = "../sp_data/sp6_data/benchmark_set_sp5.fasta"
    file_new = "../sp_data/sp6_data/train_set.fasta"
    id2seq = {}
    id2lg = {}
    id2type = {}
    id2truelbls = {}
    ids_benchmark_sp5 = []
    for seq_record in SeqIO.parse(file, "fasta"):
        ids_benchmark_sp5.append(seq_record.id.split("|")[0])
    for seq_record in SeqIO.parse(file_new, "fasta"):
        if seq_record.id.split("|")[0] in ids_benchmark_sp5:
            id2seq[seq_record.id.split("|")[0]] = str(seq_record.seq[:len(seq_record.seq) // 2])
            id2truelbls[seq_record.id.split("|")[0]] = str(seq_record.seq[len(seq_record.seq) // 2:])
            id2lg[seq_record.id.split("|")[0]] = str(seq_record.id.split("|")[1])
            id2type[seq_record.id.split("|")[0]] = str(seq_record.id.split("|")[2])
    lg_sptype2count = {}
    for k, v in id2lg.items():
        if v + "_" + id2type[k] not in lg_sptype2count:
            lg_sptype2count[v + "_" + id2type[k]] = 1
        else:
            lg_sptype2count[v + "_" + id2type[k]] += 1
    return id2seq, id2lg, id2type, id2truelbls


def extract_compatible_binaries_lipop():
    ind2glbl_lbl = {0: 'NO_SP', 1: 'SP', 2: 'TATLIPO', 3: 'LIPO', 4: 'TAT', 5: 'PILIN'}
    glbllbl2_ind = {v:k for k,v in ind2glbl_lbl.items()}
    id2seq, id2truelbls, id2lg, id2type = extract_id2seq_dict(file="train_set.fasta")

    id2seq_b5, id2truelbls_b5, id2lg_b5, id2type_b5 = extract_id2seq_dict(file="benchmark_set_sp5.fasta")
    for k in id2seq_b5.keys():
        if k not in id2seq:
            id2seq[k] = id2seq_b5[k]
            id2truelbls[k] = id2truelbls_b5[k]
            id2lg[k] = id2lg_b5[k]
            id2type[k] = id2type_b5[k]

    with open("sp1_sp2_fastas/results.txt", "rt") as f:
        lines = f.readlines()
    seq2sptype = {}
    seq2aalbls = {}
    sp_letter = ""
    life_grp, seqs, true_lbls, pred_lbls = [], [], [], []
    for l in lines:
        line = l.replace("#", "")
        id = line.split("_")[0].replace(" ", "")
        life_grp.append(id2lg[id] + "|" + id2type[id])
        seqs.append(id2seq[id])
        true_lbls.append(id2truelbls[id])

        if "SpI" in line and not "SpII" in line:
            seq2sptype[id2seq[id]] = glbllbl2_ind['SP']
            sp_letter = "S"
        elif "SpII" in line:
            seq2sptype[id2seq[id]] = glbllbl2_ind['LIPO']
            sp_letter = "L"
        else:
            seq2sptype[id2seq[id]] = glbllbl2_ind['NO_SP']
        if "cleavage" in line:
            cs_point = int(line.split("cleavage=")[1].split("-")[0])
            lblseq = cs_point * sp_letter + (len(id2seq[id]) -cs_point) * "O"
            seq2aalbls[id2seq[id]] = lblseq
        else:
            seq2aalbls[id2seq[id]] = "O" * len(id2seq[id])
        pred_lbls.append(seq2aalbls[id2seq[id]])
    all_recalls, all_precisions, total_positives, false_positives, predictions, all_f1_scores = \
        get_cs_acc(life_grp, seqs, true_lbls, pred_lbls, v=False, only_cs_position=False, sp_type="LIPO", sptype_preds=seq2sptype)
    print(all_recalls)
    print(all_precisions)
    tp, fn, fp = 0, 0, 0
    different_types = 0
    crct =0
    for s, pl, tl, lg in zip(seqs, pred_lbls, true_lbls, life_grp):
        if "EUKARYA" in lg and "SP" in lg and "NO_SP" not in lg:
            if -1 <= pl.rfind("S") - tl.rfind("S") <= 1:
                tp += 1
            else:
                fn += 1
        if "LIPO" in lg and "NO_SP" not in lg and pl[0] != tl[0]:
            different_types+=1
        elif "LIPO" in lg and "NO_SP" not in lg:
            crct +=1
    print(different_types, crct)
    print(tp/(tp+fn), tp, fn)
    # pickle.dump(seq2sptype, open("lipoP_0_1_best_sptype.bin", "wb"))
    # pickle.dump(seq2aalbls, open("lipoP_0_1.bin", "wb"))
    # for l in lines:

def extract_compatible_binaries_deepsig():
    ind2glbl_lbl = {0: 'NO_SP', 1: 'SP', 2: 'TATLIPO', 3: 'LIPO', 4: 'TAT', 5: 'PILIN'}
    glbllbl2_ind = {v:k for k,v in ind2glbl_lbl.items()}
    id2seq, id2lg, id2type, id2truelbls = extract_id2seq_dict(file="train_set.fasta")

    # with open("sp1_sp2_fastas/results_deepsig_fullds.txt", "rt") as f:
    with open("sp1_sp2_fastas/results_deepsig_v2.txt", "rt") as f:
        lines = f.readlines()
    seq2sptype = {}
    seq2aalbls = {}
    sp_letter = ""
    life_grp, seqs, true_lbls, pred_lbls = [], [], [], []
    added_seqs = set()
    for l in lines:
        id = l.split("|")[0]
        if id in id2seq and id2seq[id] not in added_seqs:
            life_grp.append(id2lg[id] + "|" + id2type[id])
            seqs.append(id2seq[id])
            added_seqs.add(id2seq[id])
            true_lbls.append(id2truelbls[id])

            if "Signal peptide" in l:
                seq2sptype[id2seq[id]] = glbllbl2_ind['SP']
                sp_letter = "S"
                cs_point = int(l.split("Signal peptide")[1].split("\t")[2])
                lblseq = cs_point * sp_letter + (len(id2seq[id]) -cs_point) * "O"
                seq2aalbls[id2seq[id]] = lblseq
            elif id2seq[id] not in seq2sptype:
                seq2sptype[id2seq[id]] = glbllbl2_ind['NO_SP']
                seq2aalbls[id2seq[id]] = "O" * len(id2seq[id])

            pred_lbls.append(seq2aalbls[id2seq[id]])
    print(len(seqs), len(set(seqs)))
    all_recalls, all_precisions, total_positives, false_positives, predictions, all_f1_scores = \
        get_cs_acc(life_grp, seqs, true_lbls, pred_lbls, v=False, only_cs_position=False, sp_type="SP", sptype_preds=seq2sptype)
    print(all_recalls, all_precisions)
    tp, fn, fp = 0, 0, 0
    different_types = 0
    crct =0
    for s, pl, tl, lg in zip(seqs, pred_lbls, true_lbls, life_grp):
        if "EUKARYA" in lg and "SP" in lg and "NO_SP" not in lg:
            if -1 <= pl.rfind("S") - tl.rfind("S") <= 1:
                tp += 1
            else:
                fn += 1
        # if "LIPO" in lg and "NO_SP" not in lg and pl[0] != tl[0]:
        #     different_types+=1
        # elif "LIPO" in lg and "NO_SP" not in lg:
        #     crct +=1
    print(different_types, crct)
    print(tp/(tp+fn), tp, fn)
    # pickle.dump(seq2sptype, open("lipoP_0_1_best_sptype.bin", "wb"))
    # pickle.dump(seq2aalbls, open("lipoP_0_1.bin", "wb"))
    # for l in lines:

def extract_compatible_phobius_binaries():
    ind2glbl_lbl = {0: 'NO_SP', 1: 'SP', 2: 'TATLIPO', 3: 'LIPO', 4: 'TAT', 5: 'PILIN'}
    glbllbl2_ind = {v:k for k,v in ind2glbl_lbl.items()}
    file = "sp1_sp2_fastas/phobius_results.txt"
    life_grp, seqs, true_lbls, pred_lbls = [], [], [], []
    seq2sptype = {}
    seq2aalbls = {}
    with open(file, "rt") as f:
        lines = f.readlines()
    count = 0
    retain_nextl_flag = False
    id2seq, id2truelbls, id2lg, id2type = extract_id2seq_dict(file="train_set.fasta")
    sp_start, sp_end = -1, -1
    first_seq = True
    for l in lines:
        if retain_nextl_flag:
            id_, lg, sp_t = l.split(" ")[-1].split("|")[:3]
            retain_id = id_
            life_grp.append(lg + "|" + sp_t)
            true_lbls.append(id2truelbls[id_])
            seqs.append(id2seq[id_])
            retain_nextl_flag = False

        if "//" in l or l == len(lines) - 1:
            retain_nextl_flag = True
            if first_seq:
                first_seq = False
            else:
                if sp_end != -1:
                    seq2sptype[id2seq[retain_id]] = glbllbl2_ind[id2type[retain_id]] if id2type[retain_id] != "NO_SP" else glbllbl2_ind["SP"]
                    predicted_sequence = id2truelbls[retain_id][0] * sp_end if id2type[retain_id] != "NO_SP" else "S" * sp_end
                    predicted_sequence = predicted_sequence + "O" * (len(id2seq[retain_id]) - sp_end)
                    pred_lbls.append(predicted_sequence)
                    sp_end = -1
                else:
                    seq2sptype[id2seq[retain_id]] = glbllbl2_ind['NO_SP']
                    predicted_sequence = "O" * len(id2seq[retain_id])
                    pred_lbls.append(predicted_sequence)

        if "SIGNAL" in l:
            sp_end = int(' '.join(l.split()).split(" ")[3])
    common_sp6_phob_seqs = extract_phobius_trained_data()
    remove_inds = [i for i in range(len(seqs)) if seqs[i] in common_sp6_phob_seqs]
    remove_inds = []
    len_ = len(seqs)
    life_grp = [life_grp[i] for i in range(len(seqs)) if i not in remove_inds]
    true_lbls = [true_lbls[i] for i in range(len(seqs)) if i not in remove_inds]
    pred_lbls = [pred_lbls[i] for i in range(len(seqs)) if i not in remove_inds]
    seqs = [seqs[i] for i in range(len_) if i not in remove_inds]
    all_recalls, all_precisions, total_positives, false_positives, predictions, all_f1_scores = \
        get_cs_acc(life_grp, seqs, true_lbls, pred_lbls, v=False, only_cs_position=False, sp_type="SP", sptype_preds=seq2sptype)
    print(all_recalls, all_precisions)

def extract_phobius_trained_data():
    folder = "/home/alex/Desktop/work/phobius_data"
    files = os.listdir(folder)
    ids = []
    seqs = []
    for f in files:
        for seq_record in SeqIO.parse(os.path.join(folder,f), "fasta"):
            ids.append(seq_record.description.split(" ")[1])
            seq = seq_record.seq[:len(seq_record.seq) // 2]
            seq_70aa = seq[:70]
            seqs.append(seq_70aa)
            # print(str(seq_record.seq(:len(seq_record) //2)))
    id2seq, id2truelbls, id2lg, id2type = extract_id2seq_dict()
    return set(seqs).intersection(id2seq.values())

def remove_non_unique():
    file = "../sp_data/sp6_data/train_set.fasta"
    unqiue_seqs_2_info = {}
    count = 0
    for seq_record in SeqIO.parse(file, "fasta"):
        if str(seq_record.seq[:len(seq_record.seq) // 2]) in unqiue_seqs_2_info:
            count += 1
            already_added_id = unqiue_seqs_2_info[str(seq_record.seq[:len(seq_record.seq) // 2])][0]
            already_added_lbl  = unqiue_seqs_2_info[str(seq_record.seq[:len(seq_record.seq) // 2])][1]
            # print("_".join(already_added_id.split("|")[1:]), "_".join(seq_record.id.split("|")[1:]))
            # if "_".join(already_added_id.split("|")[1:]) != "_".join(seq_record.id.split("|")[1:]):
            #     print(already_added_id, seq_record.id)
            if (already_added_id.split("|")[2] == "NO_SP" or  seq_record.id.split("|")[2] == "NO_SP") and \
                already_added_lbl != seq_record.seq[len(seq_record.seq) // 2:]:
                #"_".join(already_added_id.split("|")[1:]) != "_".join(seq_record.id.split("|")[1:]):
                print("\n")
                print(already_added_id , seq_record.id )
                print(already_added_lbl)
                print(seq_record.seq[len(seq_record.seq) //2 :])
                print("\n")
        #     print(unqiue_seqs_2_info[str(seq_record.seq[:len(seq_record.seq) // 2])], seq_record.id)
        unqiue_seqs_2_info[str(seq_record.seq[:len(seq_record.seq) // 2])] = (seq_record.id, seq_record.seq[len(seq_record.seq)//2:])
    print(count)
    # import glob
    # unique_seq2info = {}
    # files = glob.glob("../sp_data/sp6_partitioned_data_sublbls*")
    # for f in files:
    #     items = pickle.load(open(f, "rb"))
    #     for k, v in items.items():
    #         if k in unique_seq2info:
    #             print(unique_seq2info[k])
    #             print((v[1:], f), "\n\n",)
    #         else:
    #             unique_seq2info[k] = (v[1:], f)

def pred_lipos():
    for tr_f in [2]:
        for t_s in ['train']:

            f = "../sp_data/sp6_partitioned_data_{}_{}.bin".format(t_s, tr_f)
            a = pickle.load(open(f, "rb"))
            for k,v in a.items():
                if v[-1] == "TATLIPO":
                    print("ok, wrong")

if __name__ == "__main__":
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="tuning_bert_tune_bert_and_tnmnt_noglobal_extendedsublbls_nodrop_folds/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=True)
    exit(1)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="tuning_bert_tune_bert_and_tnmnt_repeat_best_experiment/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=True)
    exit(1)
    # mdl2results = extract_all_param_results(only_cs_position=False,
    #                                         result_folder="tuning_bert_tune_bert_noglobal_extendedsublbls_folds/",
    #                                         compare_mdl_plots=False,
    #                                         remove_test_seqs=False,
    #                                         benchmark=True)
    # exit(1)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="tuning_bert_tune_bert_and_tnmnt_folds/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=True)
    exit(1)
    visualize_validation(run="tune_bert_and_tnmnt_folds_", folds=[0, 1],
                         folder="tuning_bert_tune_bert_and_tnmnt_folds/")
    visualize_validation(run="repeat_best_experiment_", folds=[0, 1],
                         folder="tuning_bert_tune_bert_and_tnmnt_repeat_best_experiment/")
    visualize_validation(run="tune_bert_and_tnmnt_noglobal_extendedsublbls_folds_", folds=[0, 1],
                         folder="tuning_bert_tune_bert_noglobal_extendedsublbls_folds/")
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="tuning_bert_tune_bert_noglobal_extendedsublbls_folds/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=True)
    exit(1)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="tuning_bert_tune_bert_and_tnmnt_repeat_best_experiment/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=False)
    # visualize_validation(run="tune_bert_and_tnmnt_noglobal_folds_", folds=[0, 1],
    #                      folder="tuning_bert_tune_bert_and_tnmnt_nogl/")
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="tuning_bert_tune_bert_and_tnmnt_nodrop_changeBetas/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=True)
    exit(1)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="tuning_bert_tune_bert_and_tnmnt_different_initialization/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=True)
    exit(1)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="tuning_bert_tune_bert_and_tnmnt_nogl_beam_test/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=False)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="tuning_bert_tune_bert_and_tnmnt_nogl/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=True)
    # mdl2results = extract_all_param_results(only_cs_position=False,
    #                                         result_folder="separate-glbl_trimmed_tuned_bert_embs/acc_lipos/",
    #                                         compare_mdl_plots=False,
    #                                         remove_test_seqs=False,
    #                                         benchmark=True)
    exit(1)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="tuning_bert_tune_bert_and_tnmnt_folds/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=True)
    exit(1)
    visualize_validation(run="tune_bert_and_tnmnt_folds_", folds=[1, 2],
                         folder="tuning_bert_tune_bert_and_tnmnt_folds/")
    visualize_validation(run="sanity_check_scale_input_linear_pos_enc_separate_saves_", folds=[0, 1],
                         folder="separate-glbl_sanity_check_scale_input_linear_pos_enc_separate_saves_0_1/")
    exit(1)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_trimmed_tuned_bert_embs/acc_lipos/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=False)
    exit(1)
    visualize_validation(run="tuned_bert_correct_test_embs_", folds=[0, 2],
                         folder="separate-glbl_tuned_bert_correct/")
    visualize_validation(run="tuned_bert_trimmed_d_correct_test_embs_inpdrop_", folds=[0, 1],
                         folder="separate-glbl_tuned_bert_trimmed_d/")

    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tuned_bert_correct/acc_lipos/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=False)
    exit(1)
    visualize_validation(run="tuned_bert_correct_test_embs_", folds=[0, 2],
                         folder="separate-glbl_tuned_bert_correct/")
    visualize_validation(run="cnn3_3_16_validate_on_mcc2_drop_separate_glbl_cs_", folds=[0, 1],
                         folder="separate-glbl_cnn3/")
    visualize_validation(run="v2_max_glbl_lg_deailed_sp_v1_", folds=[0, 1],
                         folder="detailed_v2_glbl_max/")
    visualize_validation(run="tnmt_train_folds_", folds=[0, 1],
                         folder="folds_0_1_tnmnt_train/")
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tuned_bert_correct/acc_lipos/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=False)
    exit(1)

    #
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tuned_bert_trimmed_d/acc_lipos/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=True)
    exit(1)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_non_tuned_trimmed_d/acc_lipos/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=True)
    exit(1)

    visualize_validation(run="tuned_bert_trimmed_d_correct_test_embs_inpdrop_", folds=[0, 2],
                         folder="separate-glbl_tuned_bert_trimmed_d/")

    visualize_validation(run="non_tuned_trimmed_d_correct_test_embs_inpdrop_", folds=[0, 2],
                         folder="separate-glbl_non_tuned_trimmed_d/")

    exit(1)

    correct_duplicates_training_data()
    exit(1)
    # pred_lipos()
    # exit(1)

    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_account_lipos_rerun_separate_save_long_run/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    exit(1)
    correct_duplicates_training_data()
    exit(1)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tuned_bert_lrgdrp/acc_lipos/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=True)
    exit(1)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tuned_bert_val_on_loss/acc_lipos/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=True)
    exit(1)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tuned_bert_correct/acc_lipos/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=True)
    exit(1)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tuned_bert_nodrop_val_on_loss/acc_lipos/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=True)
    exit(1)

    extract_compatible_binaries_deepsig()
    exit(1)
    extract_compatible_binaries_deepsig()
    exit(1)
    extract_compatible_binaries_deepsig()
    exit(1)
    extract_id2seq_dict()
    remove_non_unique()
    exit(1)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tuned_bert_val_on_loss/acc_lipos/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=False)
    exit(1)
    visualize_validation(run="account_lipos_rerun_separate_save_long_run_", folds=[0, 1], folder="separate-glbl_account_lipos_rerun_separate_save_long_run/")
    exit(1)
    extract_compatible_binaries_deepsig()
    extract_compatible_binaries_deepsig()
    exit(1)
    visualize_validation(run="account_lipos_rerun_separate_save_long_run_", folds=[0, 2], folder="separate-glbl_account_lipos_rerun_separate_save_long_run/")


    exit(1)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tuned_bert_correct/acc_lipos/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=True)
    exit(1)
    prep_sp1_sp2()
    exit(1)
    # visualize_validation(run="tuned_bert_correct_test_embs_", folds=[1, 2], folder="separate-glbl_tuned_bert_correct/")

    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tuned_bert_correct/acc_lipos/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=True)
    exit(1)
    extract_compatible_binaries_deepsig()
    exit(1)
    # extract_compatible_binaries_deepsig()
    # exit(1)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tuned_bert_correct/acc_lipos/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=True)
    exit(1)
    extract_compatible_binaries_deepsig()
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_account_lipos_rerun_separate_save_long_run/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False,
                                            benchmark=False)
    exit(1)

    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_account_lipos_rerun_separate_save_long_run/only_cs/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    exit(1)
    exit(1)
    extract_compatible_binaries_deepsig()
    exit(1)
    prep_sp1_sp2()
    exit(1)
    # extract_phobius_trained_data()
    # exit(1)
    extract_compatible_phobius_binaries()
    exit(1)
    # extract_phobius_test_data()
    # exit(1)


    # exit(1)
    # extract_compatible_binaries_lipop()
    # exit(1)


    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tuned_bert_correct_inp_drop/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    prep_sp1_sp2()
    # exit(1)
    exit(1)
    prep_sp1_sp2()
    exit(1)
    # extract_calibration_probs_for_mdl()
    # duplicate_Some_logs()
    # exit(1)
    # tuned_bert_correct_test_embs_0_1.bin
    sanity_checks(run="tuned_bert_correct_test_embs_", folder="separate-glbl_tuned_bert_correct/")
    exit(1)
    visualize_validation(run="account_lipos_rerun_separate_save_long_run_", folds=[0, 2], folder="separate-glbl_account_lipos_rerun_separate_save_long_run/")
    visualize_validation(run="tuned_bert_correct_test_embs_", folds=[0, 2], folder="separate-glbl_tuned_bert_correct/")
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tuned_bert_correct/acc_lipos/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tuned_bert_correct/only_cs/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tuned_bert_correct/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    # visualize_validation(run="tuned_bert_embs_", folds=[0, 1], folder="separate-glbl_tunedbert2/")

    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_account_lipos_rerun_separate_save_long_run/lipo_acc/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_account_lipos_rerun_separate_save_long_run/lipo_acc/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tunedbert2/only_cs/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tuned_bert_large/acc_lipos/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tuned_bert_large/only_cs/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)

    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tuned_bert_large/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tunedbert2/acc_lipos/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tunedbert2/only_cs/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tunedbert2/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_account_lipos_rerun_separate_save_long_run/lipo_acc/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tuned_bert_embs/account_lipos/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    visualize_validation(run="tuned_bert_embs_", folds=[1, 2],
                         folder="separate-glbl_tuned_bert_embs/")
    visualize_validation(run="account_lipos_rerun_separate_save_long_run_", folds=[1, 2],
                         folder="separate-glbl_account_lipos_rerun_separate_save_long_run/")

    # mdl2results = extract_all_param_results(only_cs_position=False,
    #                                         result_folder="separate-glbl_account_lipos_rerun_separate_save_long_run/",
    #                                         compare_mdl_plots=False,
    #                                         remove_test_seqs=False)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tuned_bert_embs/account_lipos/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tuned_bert_embs/only_cs/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_tuned_bert_embs/only_cs/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_account_lipos_rerun_separate_save_long_run/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_rerun_separate_save_long_run/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)



    visualize_validation(run="re_rerun_separate_save_long_run_", folds=[0, 1], folder="separate-glbl_re_rerun_separate_save_long_run/")
    visualize_validation(run="weighted_loss_separate_save_long_run_", folds=[0, 1], folder="separate-glbl_weighted_loss_separat/")
    visualize_validation(run="rerun_separate_save_long_run_", folds=[0, 1], folder="separate-glbl_rerun_separate_save_long_run/")
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_rerun_separate_save_long_run/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_re_rerun_separate_save_long_run/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_weight_lbl_loss_separ/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_weighted_loss_separat/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_re_rerun_separate_save_long_run/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    visualize_validation(run="weight_lbl_loss_separate_save_long_run_", folds=[0, 1], folder="separate-glbl_weight_lbl_loss_separ/")
    visualize_validation(run="rerun_separate_save_long_run_", folds=[0, 2], folder="separate-glbl_rerun_separate_save_long_run/")
    visualize_validation(run="large_separate_save_long_run_", folds=[0, 1], folder="separate-glbl_large_separate_save_long/")
    visualize_validation(run="weighted_loss_separate_save_long_run_", folds=[0, 1], folder="separate-glbl_weighted_loss_separat/")

    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_rerun_separate_save_long_run/only_cs/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_save_long_run/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    visualize_validation(run="rerun_3_16_validate_on_mcc2_drop_separate_glbl_cs_", folds=[1, 2], folder="separate-glbl_rerun_best/")
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_large_separate_save_long/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    visualize_validation(run="large_separate_save_long_run_", folds=[1, 2], folder="separate-glbl_large_separate_save_long/")
    visualize_validation(run="scale_input_linear_pos_enc_separate_saves_", folds=[1, 2], folder="separate-glbl_scale_input_linear/")
    visualize_validation(run="cnn3_3_32_validate_on_mcc2_drop_separate_glbl_cs_", folds=[0, 1], folder="separate-glbl_3_32_mdl/")
    visualize_validation(run="linear_pos_enc_separate_saves_", folds=[0, 1], folder="separate-glbl_linear_pos_enc/")
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_linear_pos_enc/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_no_pos_enc/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    visualize_validation(run="cnn3_3_16_validate_on_mcc2_drop_separate_glbl_cs_", folds=[1, 2], folder="separate-glbl_cnn3/")
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_patience_swa/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    visualize_validation(run="large3_validate_on_mcc2_drop_separate_glbl_cs_", folds=[0, 1], folder="separate-glbl_large3/")
    visualize_validation(run="patience_swa_model_", folds=[0, 1], folder="separate-glbl_patience_swa/")
    visualize_validation(run="large3_validate_on_mcc2_drop_separate_glbl_cs_", folds=[0, 1], folder="separate-glbl_large3/")


    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_large2_01drop_mdl/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)
    visualize_validation(run="input_drop_validate_on_mcc2_drop_separate_glbl_cs_", folds=[1, 2],
                         folder="separate-glbl_input_drop/")
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl_input_drop/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)

    visualize_validation(run="tune_cs_fromstart_v2_folds_", folds=[0, 1], folder="tune_cs_from_start/")
    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="tune_cs_from_start/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)

    visualize_validation(run="validate_on_mcc2_drop_separate_glbl_cs_", folds=[1, 2], folder="separate-glbl-mcc2-drop/")
    visualize_validation(run="tune_cs_run_", folds=[0, 1], folder="tune_cs_test/")

    mdl2results = extract_all_param_results(only_cs_position=False,
                                            result_folder="separate-glbl-mcc2/",
                                            compare_mdl_plots=False,
                                            remove_test_seqs=False)

    # visualize_validation(run="separate_glbl_cs_", folds=[0, 1],folder="separate-glbl/")
    visualize_validation(run="validate_on_mcc_separate_glbl_cs_", folds=[0, 1], folder="separate-glbl-mcc/")

    # mdl2results = extract_all_param_results(only_cs_position=False, result_folder="drop_large_crct_v2_max_glbl_lg_deailed_sp_v1/",
    #                                         compare_mdl_plots=False,
    #                                         remove_test_seqs=False)

    visualize_validation(run="crct_v2_max_glbl_lg_deailed_sp_v1_", folds=[0, 1], folder="crct_simplified_glblv2_max/")
    visualize_validation(run="parameter_search_patience_30lr_1e-05_nlayers_3_nhead_16_lrsched_step_trFlds_",
                         folds=[0, 1], folder="huge_param_search/")
    visualize_validation(run="crct_v2_max_glbl_lg_deailed_sp_v1_", folds=[0, 1], folder="crct_simplified_glblv2_max/")
    visualize_validation(run="glbl_lg_deailed_sp_v1_", folds=[0, 1], folder="glbl_deailed_sp_v1/")

    visualize_validation(run="wdrop_noglbl_val_on_test_", folds=[1, 2], folder="wlg10morepatience/")
    visualize_validation(run="wdrop_noglbl_val_on_test_", folds=[0, 2], folder="wlg10morepatience/")
    # print("huh?")
    # mdl2results = extract_all_param_results(only_cs_position=False, result_folder="results_param_s_2/")
    # mdl2results_hps = extract_all_param_results(only_cs_position=False, result_folder="results_param_s_2/")
    # visualize_training_variance(mdl2results)#, mdl2results_hps)
    # extract_mean_test_results(run="param_search_0_2048_1e-05")
    # sanity_checks()
    # visualize_validation(run="param_search_0.2_4096_1e-05_", folds=[0,2])
    # visualize_validation(run="param_search_0.2_4096_1e-05_", folds=[1,2])
    # life_grp, seqs, true_lbls, pred_lbls = extract_seq_group_for_predicted_aa_lbls(filename="w_lg_w_glbl_lbl_100ep.bin")
    # sp_pred_accs = get_pred_accs_sp_vs_nosp(life_grp, seqs, true_lbls, pred_lbls,v=True)
    # all_recalls, all_precisions, total_positives, false_positives, predictions = get_cs_acc(life_grp, seqs, true_lbls, pred_lbls)
