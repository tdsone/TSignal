import pickle
import random
from Bio import SeqIO

def split_train_test_partitions(partition, split_perc=0.1):
    lgrp_and_sptype_2_inds = {}
    for ind, (seq, lbls, glbl_info) in enumerate(zip(*partition)):
        life_grp_and_sp_type = "_".join(glbl_info.split("|")[1:3])
        if life_grp_and_sp_type in lgrp_and_sptype_2_inds:
            lgrp_and_sptype_2_inds[life_grp_and_sp_type].append(ind)
        else:
            lgrp_and_sptype_2_inds[life_grp_and_sp_type] = [ind]
    seq_test, seq_train, lbls_test, lbls_train, glbl_info_train, glbl_info_test = [],[],[],[],[],[]
    for lgrp_and_sp_type, inds in lgrp_and_sptype_2_inds.items():
        if int(len(inds) * split_perc) > 0:
            no_of_test_items = int(len(inds) * split_perc)
            test_inds = random.sample(inds, no_of_test_items)
            train_inds = set(inds) - set(test_inds)

            seq_train.extend([partition[0][tri] for tri in train_inds])
            lbls_train.extend([partition[1][tri] for tri in train_inds])
            glbl_info_train.extend([partition[2][tri] for tri in train_inds])
            seq_test.extend([partition[0][tsi] for tsi in test_inds])
            lbls_test.extend([partition[1][tsi] for tsi in test_inds])
            glbl_info_test.extend([partition[2][tsi] for tsi in test_inds])
        else:
            # if not enough samples for the life group with the specific global SP type, add samples only to the train
            # set of the partition
            seq_train.extend([partition[0][i] for i in inds])
            lbls_train.extend([partition[1][i] for i in inds])
            glbl_info_train.extend([partition[2][i] for i in inds])
    return [seq_train, lbls_train, glbl_info_train], [seq_test, lbls_test, glbl_info_test]


def create_labeled_by_sp6_partition(all_ids, all_seqs, all_lbls):
    count_types = {}
    type2someseq = {}
    partition_2_info = {}
    for i, s, l in zip(all_ids, all_seqs, all_lbls):

        life_grp, partition = i.split("|")[1], int(i.split("|")[-1])
        if i.split("|")[2] in count_types:
            count_types[i.split("|")[2]] += 1
        else:
            count_types[i.split("|")[2]] = 1
        if i.split("|")[2] not in type2someseq:
            type2someseq[i.split("|")[2]] = l

        if partition in partition_2_info:
            partition_2_info[partition][0].append(str(s))
            partition_2_info[partition][1].append(str(l))
            partition_2_info[partition][2].append(i)
        else:
            partition_2_info[partition] = [[],[],[]]
            partition_2_info[partition][0] = [str(s)]
            partition_2_info[partition][1] = [str(l)]
            partition_2_info[partition][2] = [i]
    train_partitions, test_partitions = {}, {}
    for part, info in partition_2_info.items():
        train_current_part, test_current_part = split_train_test_partitions(info)
        train_partitions[part] = train_current_part
        test_partitions[part] = test_current_part
    return partition_2_info

def create_labeled_sp6_seqs(id_and_seqs):
    ids, seqs, lbls = [], [], []
    for id_and_seq in id_and_seqs:
        seq_len = len(id_and_seq[1]) // 2
        seq_id, seq, lbl = id_and_seq[0], str(id_and_seq[1][:seq_len]), str(id_and_seq[1][seq_len:])
        lbl = 1 if ("P" in lbl or "T" in lbl or "S" in lbl or "L" in lbl) else 0
        ids.append(seq_id)
        seqs.append(seq)
        lbls.append(lbl)
    return ids, seqs, lbls


def create_files(inds, lbls, seqs, train=False):
    unique_seqs = set()
    # There are some duplicate seqs somehow. Remove them.
    inds_, lbls_, seqs_ = [], [], []
    for i,l,s in zip(inds, lbls, seqs):
        if s not in unique_seqs:
            unique_seqs.add(s)
            inds_.append(i)
            lbls_.append(l)
            seqs_.append(s)
    inds, lbls, seqs = inds_, lbls_, seqs_
    file_size = 4100
    if train:
        lbl2inds_seqs = {0: [], 1: []}
        for ind, l in enumerate(lbls):
            lbl2inds_seqs[l].append(ind)
        neg_ratio = len(lbl2inds_seqs[0]) / (len(lbl2inds_seqs[1]) + len(lbl2inds_seqs[0]))
        pos_ratio = len(lbl2inds_seqs[1]) / (len(lbl2inds_seqs[1]) + len(lbl2inds_seqs[0]))
        neg_inds, pos_inds = set(lbl2inds_seqs[0]), set(lbl2inds_seqs[1])
        datasets = []
        while neg_inds:
            current_ds_seqs = []
            current_ds_ids = []
            current_ds_lbls = []
            neg_inds_current_ds = random.sample(neg_inds, min(len(neg_inds), int(file_size * neg_ratio + 1)))
            pos_inds_current_ds = random.sample(pos_inds, min(len(pos_inds), int(file_size * pos_ratio)))
            pos_inds = pos_inds - set(pos_inds_current_ds)
            neg_inds = neg_inds - set(neg_inds_current_ds)
            current_ds_seqs.extend([seqs[i] for i in pos_inds_current_ds])
            current_ds_seqs.extend([seqs[i] for i in neg_inds_current_ds])
            current_ds_ids.extend([inds[i] for i in pos_inds_current_ds])
            current_ds_ids.extend([inds[i] for i in neg_inds_current_ds])
            current_ds_lbls.extend([lbls[i] for i in pos_inds_current_ds])
            current_ds_lbls.extend(lbls[i] for i in neg_inds_current_ds)
            datasets.append([current_ds_seqs, current_ds_lbls, current_ds_ids])
        all_lbls, all_seqs, all_ids = [], [], []
        for ds in datasets:
            all_seqs.extend(ds[0])
            all_lbls.extend(ds[1])
            all_ids.extend(ds[2])
        data = [all_seqs, all_lbls,all_ids]
        pickle.dump(data, open("raw_sp6_train_data.bin", "wb"))
    else:
        pickle.dump([seqs, lbls, inds], open("raw_sp6_bench_data.bin", "wb"))

seqs, lbls, ids, global_lbls = [], [], [], []

for seq_record in SeqIO.parse("train_set.fasta", "fasta"):
    seqs.append(seq_record.seq[:len(seq_record.seq) // 2])
    lbls.append(seq_record.seq[len(seq_record.seq) // 2:])
    ids.append(seq_record.id)


# for seq_record in SeqIO.parse("benchmark_set_sp5.fasta", "fasta"):
#     id_sequences_train.append((seq_record.id, seq_record.seq))
#     cat = get_cat(str(seq_record.seq))
#     if cat in train_categories2count:
#         train_categories2count[cat] += 1
#     elif cat not in train_categories2count:
#         train_categories2count[cat] = 1
lgandsptype2count = {}
for i,s,l in zip(ids, seqs, lbls):
    if "_".join(i.split("|")[1:3]) not in lgandsptype2count:
        lgandsptype2count["_".join(i.split("|")[1:3])] = 1
    else:
        lgandsptype2count["_".join(i.split("|")[1:3])] += 1

print(lgandsptype2count)
exit(1)
partition_2_info = create_labeled_by_sp6_partition(ids, seqs, lbls)

for part_no, info in partition_2_info.items():
    train_part_info, test_part_info = split_train_test_partitions(info)
    # the split is done evenely across all global labels in conjunction with the life group information
    pickle.dump(train_part_info, open("sp6_partitioned_data_train_{}.bin".format(part_no), "wb"))
    pickle.dump(test_part_info, open("sp6_partitioned_data_test_{}.bin".format(part_no), "wb"))
