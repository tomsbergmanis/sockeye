# Copyright 2017--2022 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may not
# use this file except in compliance with the License. A copy of the License
# is located at
#
#     http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is distributed on
# an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.

import os
import random
from tempfile import TemporaryDirectory
from typing import Optional, List, Tuple

import numpy as np
import pytest
import torch

from sockeye import constants as C
from sockeye import data_io
from sockeye import vocab
from sockeye.utils import SockeyeError, get_tokens, seed_rngs

seed_rngs(12)

define_bucket_tests = [(50, 10, [10, 20, 30, 40, 50]),
                       (50, 20, [20, 40, 50]),
                       (50, 50, [50]),
                       (5, 10, [5]),
                       (11, 5, [5, 10, 11]),
                       (19, 10, [10, 19])]


@pytest.mark.parametrize("max_seq_len, step, expected_buckets", define_bucket_tests)
def test_define_buckets(max_seq_len, step, expected_buckets):
    buckets = data_io.define_buckets(max_seq_len, step=step)
    assert buckets == expected_buckets


define_parallel_bucket_tests = [(50, 50, 10, True, 1.0, [(10, 10), (20, 20), (30, 30), (40, 40), (50, 50)]),
                                (50, 50, 10, True, 0.5,
                                 [(10, 5), (20, 10), (30, 15), (40, 20), (50, 25), (50, 30), (50, 35), (50, 40),
                                  (50, 45), (50, 50)]),
                                (10, 10, 10, True, 0.1,
                                 [(10, 2), (10, 3), (10, 4), (10, 5), (10, 6), (10, 7), (10, 8), (10, 9), (10, 10)]),
                                (10, 5, 10, True, 0.01, [(10, 2), (10, 3), (10, 4), (10, 5)]),
                                (50, 50, 10, True, 2.0,
                                 [(5, 10), (10, 20), (15, 30), (20, 40), (25, 50), (30, 50), (35, 50), (40, 50),
                                  (45, 50), (50, 50)]),
                                (5, 10, 10, True, 10.0, [(2, 10), (3, 10), (4, 10), (5, 10)]),
                                (5, 10, 10, True, 11.0, [(2, 10), (3, 10), (4, 10), (5, 10)]),
                                (50, 50, 50, True, 0.5, [(50, 25), (50, 50)]),
                                (50, 50, 50, True, 1.5, [(33, 50), (50, 50)]),
                                (75, 75, 50, True, 1.5, [(33, 50), (66, 75), (75, 75)]),
                                (50, 50, 8, False, 1.5, [(8, 8), (16, 16), (24, 24), (32, 32), (40, 40), (48, 48),
                                                         (50, 50)]),
                                (50, 75, 8, False, 1.5, [(8, 8), (16, 16), (24, 24), (32, 32), (40, 40), (48, 48),
                                                         (50, 56), (50, 64), (50, 72), (50, 75)])]


@pytest.mark.parametrize("max_seq_len_source, max_seq_len_target, bucket_width, bucket_scaling, length_ratio,"
                         "expected_buckets", define_parallel_bucket_tests)
def test_define_parallel_buckets(max_seq_len_source, max_seq_len_target, bucket_width, bucket_scaling, length_ratio,
                                 expected_buckets):
    buckets = data_io.define_parallel_buckets(max_seq_len_source, max_seq_len_target, bucket_width=bucket_width,
                                              bucket_scaling=bucket_scaling, length_ratio=length_ratio)
    assert buckets == expected_buckets


get_bucket_tests = [([10, 20, 30, 40, 50], 50, 50),
                    ([10, 20, 30, 40, 50], 11, 20),
                    ([10, 20, 30, 40, 50], 9, 10),
                    ([10, 20, 30, 40, 50], 51, None),
                    ([10, 20, 30, 40, 50], 1, 10),
                    ([10, 20, 30, 40, 50], 0, 10),
                    ([], 50, None)]


@pytest.mark.parametrize("buckets, length, expected_bucket",
                         get_bucket_tests)
def test_get_bucket(buckets, length, expected_bucket):
    bucket = data_io.get_bucket(length, buckets)
    assert bucket == expected_bucket


tokens2ids_tests = [(["a", "b", "c"], {"a": 1, "b": 0, "c": 300, C.UNK_SYMBOL: 12}, [1, 0, 300]),
                    (["a", "x", "c"], {"a": 1, "b": 0, "c": 300, C.UNK_SYMBOL: 12}, [1, 12, 300])]


@pytest.mark.parametrize("tokens, vocab, expected_ids", tokens2ids_tests)
def test_tokens2ids(tokens, vocab, expected_ids):
    ids = data_io.tokens2ids(tokens, vocab)
    assert ids == expected_ids


@pytest.mark.parametrize("tokens, expected_ids", [(["1", "2", "3", "0"], [1, 2, 3, 0]), ([], [])])
def test_strids2ids(tokens, expected_ids):
    ids = data_io.strids2ids(tokens)
    assert ids == expected_ids


sequence_reader_tests = [(["1 2 3", "2", "", "2 2 2"], False, False, False),
                         (["a b c", "c"], True, False, False),
                         (["a b c", ""], True, False, False),
                         (["a b c", "c"], True, True, True)]


@pytest.mark.parametrize("sequences, use_vocab, add_bos, add_eos", sequence_reader_tests)
def test_sequence_reader(sequences, use_vocab, add_bos, add_eos):
    with TemporaryDirectory() as work_dir:
        path = os.path.join(work_dir, 'input')
        with open(path, 'w') as f:
            for sequence in sequences:
                print(sequence, file=f)

        vocabulary = vocab.build_vocab(sequences) if use_vocab else None

        reader = data_io.SequenceReader(path, vocabulary=vocabulary, add_bos=add_bos, add_eos=add_eos)

        read_sequences = [s for s in reader]
        assert len(read_sequences) == len(sequences)

        if vocabulary is None:
            with pytest.raises(SockeyeError) as e:
                data_io.SequenceReader(path, vocabulary=vocabulary, add_bos=True)
            assert str(e.value) == "Adding a BOS or EOS symbol requires a vocabulary"

            expected_sequences = [data_io.strids2ids(get_tokens(s)) if s else None for s in sequences]
            assert read_sequences == expected_sequences
        else:
            expected_sequences = [data_io.tokens2ids(get_tokens(s), vocabulary) if s else None for s in sequences]
            if add_bos:
                expected_sequences = [[vocabulary[C.BOS_SYMBOL]] + s if s else None for s in expected_sequences]
            if add_eos:
                expected_sequences = [s + [vocabulary[C.EOS_SYMBOL]] if s else None for s in expected_sequences]
            assert read_sequences == expected_sequences


def test_alignment_reader():

    inputs = [r'{"a": 1, "b": 0, "c": 0.5}', r'{}']
    expected_data_no_vocab = [[['a', 'b', 'c'], [1., 0., 0.5]], None]

    with TemporaryDirectory() as work_dir:
        path = os.path.join(work_dir, 'input')
        with open(path, 'w') as f:
            for inp in inputs:
                print(inp, file=f)

        vocabulary = vocab.build_from_paths([path], is_alignment=True)
        reader = data_io.AlignmentReader(path, vocabulary=vocabulary)

        read_data = [d for d in reader]
        assert len(read_data) == len(inputs)

        for data, expected_output in zip(read_data, expected_data_no_vocab):
            if expected_output is not None:
                expected_output = [data_io.tokens2ids(expected_output[0], vocabulary), expected_output[1]]
            assert data == expected_output


@pytest.mark.parametrize("source_iterables, target_iterables",
                         [
                             (
                                     [[[0], [1, 1], [2], [3, 3, 3]], [[0], [1, 1], [2], [3, 3, 3]]],
                                     [[[0], [1]]]
                             ),
                             (
                                     [[[0], [1, 1]], [[0], [1, 1]]],
                                     [[[0], [1, 1], [2], [3, 3, 3]]]
                             ),
                             (
                                     [[[0], [1, 1]]],
                                     [[[0], [1, 1], [2], [3, 3, 3]]]
                             ),
                         ])
def test_nonparallel_iter(source_iterables, target_iterables):
    with pytest.raises(SockeyeError) as e:
        list(data_io.parallel_iter(source_iterables, target_iterables))
    assert str(e.value) == "Different number of lines in source(s), target(s), and (if specified) alignment iterables."


@pytest.mark.parametrize("source_iterables, target_iterables",
                         [
                             (
                                     [[[0], [1, 1]], [[0], [1]]],
                                     [[[0], [1]]]
                             )
                         ])
def test_not_source_token_parallel_iter(source_iterables, target_iterables):
    with pytest.raises(SockeyeError) as e:
        list(data_io.parallel_iter(source_iterables, target_iterables))
    assert str(e.value).startswith("Source sequences are not token-parallel")


@pytest.mark.parametrize("source_iterables, target_iterables",
                         [
                             (
                                     [[[0], [1]]],
                                     [[[0], [1, 1]], [[0], [1]]],
                             )
                         ])
def test_not_target_token_parallel_iter(source_iterables, target_iterables):
    with pytest.raises(SockeyeError) as e:
        list(data_io.parallel_iter(source_iterables, target_iterables))
    assert str(e.value).startswith("Target sequences are not token-parallel")


@pytest.mark.parametrize("source_iterables, target_iterables, alignment_iterable, expected",
                         [
                             # Without alignment
                             (
                                     [[[0], [1, 1]], [[0], [1, 1]]],
                                     [[[0], [1]]],
                                     None,
                                     [([[0], [0]], [[0]], None), ([[1, 1], [1, 1]], [[1]], None)]
                             ),
                             (
                                     [[[0], None], [[0], None]],
                                     [[[0], [1]]],
                                     None,
                                     [([[0], [0]], [[0]], None)]
                             ),
                             (
                                     [[[0], [1, 1]], [[0], [1, 1]]],
                                     [[[0], None]],
                                     None,
                                     [([[0], [0]], [[0]], None)]
                             ),
                             (
                                     [[None, [1, 1]], [None, [1, 1]]],
                                     [[None, [1]]],
                                     None,
                                     [([[1, 1], [1, 1]], [[1]], None)]
                             ),
                             (
                                     [[None, [1]]],
                                     [[None, [1, 1]], [None, [1, 1]]],
                                     None,
                                     [([[1]], [[1, 1], [1, 1]], None)]
                             ),
                             (
                                     [[None, [1, 1]], [None, [1, 1]]],
                                     [[None, None]],
                                     None,
                                     []
                             ),
                             # With alignment
                             (
                                     [[[0], [1, 1]], [[0], [1, 1]]],
                                     [[[0], [1]]],
                                     [2, 3],
                                     [([[0], [0]], [[0]], 2), ([[1, 1], [1, 1]], [[1]], 3)]
                             ),
                             (
                                     [[[0], None], [[0], None]],
                                     [[[0], [1]]],
                                     [2, 3],
                                     [([[0], [0]], [[0]], 2)]
                             ),
                             (
                                     [[None, [1, 1]], [None, [1, 1]]],
                                     [[None, None]],
                                     [2, 3],
                                     []
                             ),
                         ])
def test_parallel_iter(source_iterables, target_iterables, alignment_iterable, expected):
    assert list(data_io.parallel_iter(source_iterables, target_iterables, alignment_iterable)) == expected


def test_sample_based_define_bucket_batch_sizes():
    batch_type = C.BATCH_TYPE_SENTENCE
    batch_size = 32
    max_seq_len = 100
    buckets = data_io.define_parallel_buckets(max_seq_len, max_seq_len, 10, True, 1.5)
    bucket_batch_sizes = data_io.define_bucket_batch_sizes(buckets=buckets,
                                                           batch_size=batch_size,
                                                           batch_type=batch_type,
                                                           data_target_average_len=[None] * len(buckets))
    for bbs in bucket_batch_sizes:
        assert bbs.batch_size == batch_size
        assert bbs.average_target_words_per_batch == bbs.bucket[1] * batch_size


@pytest.mark.parametrize("length_ratio,batch_sentences_multiple_of,expected_batch_sizes", [
    # Reference batch sizes manually inspected for sanity.
    (0.5, 1, [200, 100, 67, 50, 40, 33, 29, 25, 22, 20]),
    (1.5, 1, [100, 50, 33, 25, 20, 20, 20, 20]),
    (1.5, 8, [96, 48, 32, 24, 16, 16, 16, 16])])
def test_word_based_define_bucket_batch_sizes(length_ratio, batch_sentences_multiple_of, expected_batch_sizes):
    batch_type = C.BATCH_TYPE_WORD
    batch_size = 1000
    max_seq_len = 50
    buckets = data_io.define_parallel_buckets(max_seq_len, max_seq_len, 10, True, length_ratio)
    bucket_batch_sizes = data_io.define_bucket_batch_sizes(buckets=buckets,
                                                           batch_size=batch_size,
                                                           batch_type=batch_type,
                                                           data_target_average_len=[None] * len(buckets),
                                                           batch_sentences_multiple_of=batch_sentences_multiple_of)
    for bbs, expected_batch_size in zip(bucket_batch_sizes, expected_batch_sizes):
        assert bbs.batch_size == expected_batch_size
        expected_average_target_words_per_batch = expected_batch_size * bbs.bucket[1]
        assert bbs.average_target_words_per_batch == expected_average_target_words_per_batch


@pytest.mark.parametrize("length_ratio,batch_sentences_multiple_of,expected_batch_sizes", [
    # Reference batch sizes manually inspected for sanity.
    (0.5, 1, [200, 100, 66, 50, 40, 33, 28, 25, 22, 20]),
    (1.5, 1, [100, 50, 33, 25, 20, 20, 20, 20]),
    (1.5, 8, [96, 48, 32, 24, 16, 16, 16, 16])])
def test_max_word_based_define_bucket_batch_sizes(length_ratio, batch_sentences_multiple_of, expected_batch_sizes):
    batch_type = C.BATCH_TYPE_MAX_WORD
    batch_size = 1000
    max_seq_len = 50
    buckets = data_io.define_parallel_buckets(max_seq_len, max_seq_len, 10, True, length_ratio)
    bucket_batch_sizes = data_io.define_bucket_batch_sizes(buckets=buckets,
                                                           batch_size=batch_size,
                                                           batch_type=batch_type,
                                                           data_target_average_len=[None] * len(buckets),
                                                           batch_sentences_multiple_of=batch_sentences_multiple_of)
    for bbs, expected_batch_size in zip(bucket_batch_sizes, expected_batch_sizes):
        assert bbs.batch_size == expected_batch_size
        expected_average_target_words_per_batch = expected_batch_size * bbs.bucket[1]
        assert bbs.average_target_words_per_batch == expected_average_target_words_per_batch


def test_compute_slice_indices_from_sequence_lengths():
    seq_lens = torch.tensor([0, 1, 2, 0, 0, 3, 4, 5, 0])
    slice_indices = torch.tensor([[0, 0], [0, 1], [1, 3], [3, 3], [3, 3], [3, 6], [6, 10], [10, 15], [15, 15]])
    assert torch.equal(data_io.compute_slice_indices_from_sequence_lengths(seq_lens), slice_indices)


def _compare_alignment_tensors(name_ids1, weights1, slice_indices1, name_ids2, weights2, slice_indices2):
        # Equal
        assert name_ids1.dtype == name_ids2.dtype
        assert torch.equal(name_ids1, name_ids2)
        # All close
        assert weights1.dtype == weights2.dtype
        assert torch.allclose(weights1, weights2)
        # Equal
        assert slice_indices1.dtype == slice_indices2.dtype
        assert torch.equal(slice_indices1, slice_indices2)


@pytest.mark.parametrize("alignment_tuple_list,alignment_tensors", [
    ([(np.array([0], dtype='int32'), np.array([1.], dtype='float32'))],
     (torch.tensor([0], dtype=torch.int32),
      torch.tensor([1.], dtype=torch.float32),
      torch.tensor([[0, 1]], dtype=torch.int64))),

    ([(np.array([1, 2], dtype='int32'), np.array([0.5, 0.5], dtype='float32')),
      (np.array([0], dtype='int32'), np.array([1.], dtype='float32')),
      (np.array([3, 4, 5], dtype='int32'), np.array([0.33, 0.33, 0.33], dtype='float32'))],
     (torch.tensor([1, 2, 0, 3, 4, 5], dtype=torch.int32),
      torch.tensor([0.5, 0.5, 1., 0.33, 0.33, 0.33], dtype=torch.float32),
      torch.tensor([[0, 2], [2, 3], [3, 6]], dtype=torch.int64))),

    ([],
     (torch.zeros(0, dtype=torch.int32),
      torch.zeros(0, dtype=torch.float32),
      torch.zeros(0, 2, dtype=torch.int64)))
])
def test_alignment_bucket_creation(alignment_tuple_list, alignment_tensors):

    # Test packing and conversion
    alignment_bucket = data_io.AlignmentBucket.from_numpy_tuple_list(alignment_tuple_list)
    _compare_alignment_tensors(*alignment_bucket.as_tuple(), *alignment_tensors)
    assert len(alignment_bucket) == len(alignment_tuple_list)

    # Test slicing individual sequences
    for i, (name_ids_np, weights_np) in enumerate(alignment_tuple_list):
        name_ids, weights = alignment_bucket.get(i)
        assert torch.equal(name_ids, torch.tensor(name_ids_np))
        assert torch.allclose(weights, torch.tensor(weights_np))

    # Test tuple round trip
    alignment_bucket_rt = data_io.AlignmentBucket(*alignment_bucket.as_tuple())
    _compare_alignment_tensors(*alignment_bucket_rt.as_tuple(), *alignment_tensors)


@pytest.mark.parametrize("start,end,expected_batch", [
    (0, 0, (torch.zeros(0, 0, dtype=torch.int32), torch.zeros(0, 0, dtype=torch.float32))),
    (0, 1, (torch.tensor([[]], dtype=torch.int32), torch.tensor([[]], dtype=torch.float32))),
    (0, 2, (torch.tensor([[], []], dtype=torch.int32), torch.tensor([[], []], dtype=torch.float32))),
    (0, 2, (torch.tensor([[], []], dtype=torch.int32), torch.tensor([[], []], dtype=torch.float32))),
    (2, 2, (torch.zeros(0, 0, dtype=torch.int32), torch.zeros(0, 0, dtype=torch.float32))),
    (2, 3, (torch.tensor([[0, 1]], dtype=torch.int32), torch.tensor([[0.5, 0.5]], dtype=torch.float32))),
    (2, 4, (torch.tensor([[0, 1], [0, C.PAD_ID]], dtype=torch.int32),
            torch.tensor([[0.5, 0.5], [1., 0.]], dtype=torch.float32))),
    (2, 5, (torch.tensor([[0, 1, C.PAD_ID, C.PAD_ID],
                         [0, C.PAD_ID, C.PAD_ID, C.PAD_ID],
                         [0, 1, 2, 3]], dtype=torch.int32),
            torch.tensor([[0.5, 0.5, 0., 0.], [1., 0., 0., 0.], [0.25, 0.25, 0.25, 0.25]], dtype=torch.float32))),
    (5, 8, (torch.tensor([[0, 1, 2, C.PAD_ID, C.PAD_ID],
                          [C.PAD_ID, C.PAD_ID, C.PAD_ID, C.PAD_ID, C.PAD_ID],
                          [0, 1, 2, 3, 4]], dtype=torch.int32),
            torch.tensor([[0.33, 0.33, 0.33, 0., 0.],
                          [0., 0., 0., 0., 0.],
                          [0.2, 0.2, 0.2, 0.2, 0.2]], dtype=torch.float32))),
])
def test_alignment_bucket_get_batch(start, end, expected_batch):
    alignment_tuple_list = [
        (np.array([], dtype='int32'), np.array([], dtype='float32')),
        (np.array([], dtype='int32'), np.array([], dtype='float32')),
        (np.array([0, 1], dtype='int32'), np.array([0.5, 0.5], dtype='float32')),
        (np.array([0], dtype='int32'), np.array([1.], dtype='float32')),
        (np.array([0, 1, 2, 3], dtype='int32'), np.array([0.25, 0.25, 0.25, 0.25], dtype='float32')),
        (np.array([0, 1, 2], dtype='int32'), np.array([0.33, 0.33, 0.33], dtype='float32')),
        (np.array([], dtype='int32'), np.array([], dtype='float32')),
        (np.array([0, 1, 2, 3, 4], dtype='int32'), np.array([0.2, 0.2, 0.2, 0.2, 0.2], dtype='float32')),
    ]
    alignment_bucket = data_io.AlignmentBucket.from_numpy_tuple_list(alignment_tuple_list)
    batch = alignment_bucket.get_batch(start, end)
    assert batch[0].dtype == expected_batch[0].dtype
    assert torch.equal(batch[0], expected_batch[0])
    assert batch[1].dtype == expected_batch[1].dtype
    assert torch.allclose(batch[1], expected_batch[1])


alignment_tuple_lists = [
    [],
    [(np.array([0], dtype='int32'), np.array([1.], dtype='float32')),
     (np.array([0, 1], dtype='int32'), np.array([0.5, 0.5], dtype='float32')),
     (np.array([0, 1, 2], dtype='int32'), np.array([0.33, 0.33, 0.33], dtype='float32')),
     (np.array([0, 1, 2, 3], dtype='int32'), np.array([0.25, 0.25, 0.25, 0.25], dtype='float32')),
     (np.array([0, 1, 2, 3, 4], dtype='int32'), np.array([0.2, 0.2, 0.2, 0.2, 0.2], dtype='float32')),
    ],
    [(np.array([], dtype='int32'), np.array([], dtype='float32')),
     (np.array([0], dtype='int32'), np.array([1.], dtype='float32')),
     (np.array([0, 1], dtype='int32'), np.array([0.5, 0.5], dtype='float32')),
     (np.array([0, 1, 2], dtype='int32'), np.array([0.33, 0.33, 0.33], dtype='float32')),
     (np.array([], dtype='int32'), np.array([], dtype='float32')),
     (np.array([], dtype='int32'), np.array([], dtype='float32')),
     (np.array([0, 1, 2, 3, 4], dtype='int32'), np.array([0.2, 0.2, 0.2, 0.2, 0.2], dtype='float32')),
     (np.array([0, 1, 2, 3], dtype='int32'), np.array([0.25, 0.25, 0.25, 0.25], dtype='float32')),
     (np.array([0], dtype='int32'), np.array([1.], dtype='float32')),
     (np.array([], dtype='int32'), np.array([], dtype='float32')),
    ],
]


@pytest.mark.parametrize("alignment_tuple_list", alignment_tuple_lists)
def test_alignment_bucket_slice_copy(alignment_tuple_list):
    alignment_bucket = data_io.AlignmentBucket.from_numpy_tuple_list(alignment_tuple_list)
    # For various slice sizes taken from various positions in the alignment...
    for slice_size in {0, 1, 2, len(alignment_tuple_list) // 2, len(alignment_tuple_list)}:
        for start in range(0, len(alignment_tuple_list)):
            end = start + slice_size
            # Check that the sliced AlignmentBucket is identical to the
            # AlignmentBucket created from the slice of the original tuple list
            # using the same indices.
            sliced_alignment_bucket = alignment_bucket.slice_copy(start, end)
            alignment_bucket_from_slice = data_io.AlignmentBucket.from_numpy_tuple_list(alignment_tuple_list[start:end])
            _compare_alignment_tensors(*sliced_alignment_bucket.as_tuple(), *alignment_bucket_from_slice.as_tuple())


@pytest.mark.parametrize("alignment_tuple_list", alignment_tuple_lists)
def test_alignment_bucket_index_select(alignment_tuple_list):
    if len(alignment_tuple_list) <= 0:
        # Cannot select from buckets of size 0
        return
    indices = random.choices(range(len(alignment_tuple_list) - 1), k=10)
    # Test: create AlignmentBucket from tuple list and then call index_select
    alignment_bucket = data_io.AlignmentBucket.from_numpy_tuple_list(alignment_tuple_list)
    selected_alignment_bucket = alignment_bucket.index_select(torch.tensor(indices))
    # Reference: create tuple list from selected indices and then create
    # AlignmentBucket
    selected_tuple_list = [alignment_tuple_list[i] for i in indices]
    alignment_bucket_from_selected = alignment_bucket.from_numpy_tuple_list(selected_tuple_list)
    _compare_alignment_tensors(*selected_alignment_bucket.as_tuple(), *alignment_bucket_from_selected.as_tuple())


@pytest.mark.parametrize("alignment_tuple_list", alignment_tuple_lists)
def test_alignment_bucket_repeat(alignment_tuple_list):
    alignment_bucket = data_io.AlignmentBucket.from_numpy_tuple_list(alignment_tuple_list)
    # For various numbers of repeats...
    for repeats in (0, 1, 2, 5):
        # Check that the repeated AlignmentBucket is identical to the
        # AlignmentBucket created from repeating the original tuple list.
        repeated_alignment_bucket = alignment_bucket.repeat(repeats)
        alignment_bucket_from_repeated = data_io.AlignmentBucket.from_numpy_tuple_list(alignment_tuple_list * repeats)
        _compare_alignment_tensors(*repeated_alignment_bucket.as_tuple(), *alignment_bucket_from_repeated.as_tuple())


@pytest.mark.parametrize("alignment_tuple_list", alignment_tuple_lists)
def test_alignment_bucket_fill_up(alignment_tuple_list):
    if len(alignment_tuple_list) <= 0:
        # Cannot fill up buckets of size 0
        return
    desired_indices = random.choices(range(len(alignment_tuple_list)), k=10)
    # Test: create AlignmentBucket from tuple list and then call fill_up
    alignment_bucket = data_io.AlignmentBucket.from_numpy_tuple_list(alignment_tuple_list)
    filled_up_alignment_bucket = alignment_bucket.fill_up(torch.tensor(desired_indices))
    # Reference: fill up tuple list and then create AlignmentBucket
    filled_up_alignment_tuple_list = alignment_tuple_list + [alignment_tuple_list[i] for i in desired_indices]
    alignment_bucket_from_filled_up = data_io.AlignmentBucket.from_numpy_tuple_list(filled_up_alignment_tuple_list)
    _compare_alignment_tensors(*filled_up_alignment_bucket.as_tuple(), *alignment_bucket_from_filled_up.as_tuple())


def _get_random_bucketed_data(
    buckets: List[Tuple[int, int]],
    min_count: int,
    max_count: int,
    bucket_counts: Optional[List[Optional[int]]] = None,
    include_alignment: bool = False) -> Tuple[List[torch.Tensor],
                                             List[torch.Tensor],
                                             Optional[List[data_io.AlignmentBucket]]]:
    """
    Get random bucket data.

    :param buckets: The list of buckets.
    :param min_count: The minimum number of samples that will be sampled if no exact count is given.
    :param max_count: The maximum number of samples that will be sampled if no exact count is given.
    :param bucket_counts: For each bucket an optional exact example count can be given. If it is not given it will be
                          sampled.
    :param include_alignment: Also generate random alignment (otherwise return None for alignment).
    :return: The random source and target tensors and optional alignment.
    """
    if bucket_counts is None:
        bucket_counts = [None for _ in buckets]
    bucket_counts = [random.randint(min_count, max_count) if given_count is None else given_count
                     for given_count in bucket_counts]
    source = [torch.randint(0, 10, (count, random.randint(1, bucket[0]), 1))
              for count, bucket in zip(bucket_counts, buckets)]
    target = [torch.randint(0, 10, (count, random.randint(2, bucket[1]), 1))
              for count, bucket in zip(bucket_counts, buckets)]
    alignment = None
    if include_alignment:
        alignment = []
        for count, bucket in zip(bucket_counts, buckets):
            alignment_tuple_list = []
            for _ in range(count):
                name_ids = np.random.randint(0, 10, (random.randint(0, bucket[0]),))
                weights = np.random.rand(*name_ids.shape)
                alignment_tuple_list.append((name_ids, weights))
            alignment.append(data_io.AlignmentBucket.from_numpy_tuple_list(alignment_tuple_list))
    return source, target, alignment


@pytest.mark.parametrize("include_alignment", [False, True])
def test_parallel_data_set(include_alignment):
    buckets = data_io.define_parallel_buckets(100, 100, 10, True, 1.0)
    source, target, alignment = _get_random_bucketed_data(buckets, min_count=0, max_count=5,
                                                         include_alignment=include_alignment)

    def check_equal(tensors1, tensors2):
        assert len(tensors1) == len(tensors2)
        for a1, a2 in zip(tensors1, tensors2):
            assert torch.equal(a1, a2)

    def check_equal_alignment(alignment1, alignment2):
        assert len(alignment1) == len(alignment2)
        for md1, md2 in zip(alignment1, alignment2):
            assert len(md1) == len(md2)
            for i in range(len(md1)):
                name_ids1, weights1 = md1.get(i)
                name_ids2, weights2 = md2.get(i)
                assert torch.equal(name_ids1, name_ids2)
                assert torch.allclose(weights1, weights2)

    with TemporaryDirectory() as work_dir:
        dataset = data_io.ParallelDataSet(source, target, alignment)
        fname = os.path.join(work_dir, 'dataset')
        dataset.save(fname)
        dataset_loaded = data_io.ParallelDataSet.load(fname)
        check_equal(dataset.source, dataset_loaded.source)
        check_equal(dataset.target, dataset_loaded.target)
        if include_alignment:
            check_equal_alignment(dataset.alignment, dataset_loaded.alignment)
        else:
            # Test backward compatibility: with the legacy format (source/target
            # only; no alignment)
            dataset.save(fname, use_legacy_format=True)
            dataset_loaded = data_io.ParallelDataSet.load(fname)
            check_equal(dataset.source, dataset_loaded.source)
            check_equal(dataset.target, dataset_loaded.target)


@pytest.mark.parametrize("include_alignment", [False, True])
def test_parallel_data_set_fill_up(include_alignment):
    batch_size = 32
    buckets = data_io.define_parallel_buckets(100, 100, 10, True, 1.0)
    bucket_batch_sizes = data_io.define_bucket_batch_sizes(buckets,
                                                           batch_size,
                                                           batch_type=C.BATCH_TYPE_SENTENCE,
                                                           data_target_average_len=[None] * len(buckets))
    dataset = data_io.ParallelDataSet(*_get_random_bucketed_data(buckets, min_count=1, max_count=5,
                                                                 include_alignment=include_alignment))

    dataset_filled_up = dataset.fill_up(bucket_batch_sizes)
    assert len(dataset_filled_up.source) == len(dataset.source)
    assert len(dataset_filled_up.target) == len(dataset.target)
    for bidx in range(len(dataset)):
        bucket_batch_size = bucket_batch_sizes[bidx].batch_size
        assert dataset_filled_up.source[bidx].shape[0] == bucket_batch_size
        assert dataset_filled_up.target[bidx].shape[0] == bucket_batch_size


def test_get_permutations():
    data = [list(range(3)), list(range(1)), list(range(7)), []]
    bucket_counts = [len(d) for d in data]

    permutation, inverse_permutation = data_io.get_permutations(bucket_counts)
    assert len(permutation) == len(inverse_permutation) == len(bucket_counts) == len(data)

    for d, p, pi in zip(data, permutation, inverse_permutation):
        p_set = set(p.tolist())
        pi_set = set(pi.tolist())
        assert len(p_set) == len(p)
        assert len(pi_set) == len(pi)
        assert p_set - pi_set == set()
        if d:
            d = torch.tensor(d)
            assert (d[p][pi] == d).all()
        else:
            assert len(p_set) == 1


@pytest.mark.parametrize("include_alignment", [False, True])
def test_parallel_data_set_permute(include_alignment):
    batch_size = 5
    buckets = data_io.define_parallel_buckets(100, 100, 10, True, 1.0)
    bucket_batch_sizes = data_io.define_bucket_batch_sizes(buckets,
                                                           batch_size,
                                                           batch_type=C.BATCH_TYPE_SENTENCE,
                                                           data_target_average_len=[None] * len(buckets))
    dataset = data_io.ParallelDataSet(*_get_random_bucketed_data(buckets, min_count=0, max_count=5,
                                                                 include_alignment=include_alignment)).fill_up(
        bucket_batch_sizes)

    permutations, inverse_permutations = data_io.get_permutations(dataset.get_bucket_counts())

    assert len(permutations) == len(inverse_permutations) == len(dataset)
    dataset_restored = dataset.permute(permutations).permute(inverse_permutations)
    assert len(dataset) == len(dataset_restored)
    for buck_idx in range(len(dataset)):
        num_samples = dataset.source[buck_idx].shape[0]
        if num_samples:
            assert (dataset.source[buck_idx] == dataset_restored.source[buck_idx]).all()
            assert (dataset.target[buck_idx] == dataset_restored.target[buck_idx]).all()
            if include_alignment:
                _compare_alignment_tensors(*dataset.alignment[buck_idx].as_tuple(),
                                          *dataset_restored.alignment[buck_idx].as_tuple())
        else:
            assert not dataset_restored.source[buck_idx].shape[0]
            assert not dataset_restored.target[buck_idx].shape[0]
            if include_alignment:
                assert not len(dataset_restored.alignment[buck_idx])


def test_get_batch_indices():
    max_bucket_size = 50
    batch_size = 10
    buckets = data_io.define_parallel_buckets(100, 100, 10, True, 1.0)
    bucket_batch_sizes = data_io.define_bucket_batch_sizes(buckets,
                                                           batch_size,
                                                           batch_type=C.BATCH_TYPE_SENTENCE,
                                                           data_target_average_len=[None] * len(buckets))
    dataset = data_io.ParallelDataSet(*_get_random_bucketed_data(buckets=buckets,
                                                                 min_count=1,
                                                                 max_count=max_bucket_size))

    indices = data_io.get_batch_indices(dataset, bucket_batch_sizes=bucket_batch_sizes)

    # check for valid indices
    for buck_idx, start_pos in indices:
        assert 0 <= buck_idx < len(dataset)
        assert 0 <= start_pos < len(dataset.source[buck_idx]) - batch_size + 1

    # check that all indices are used for a filled-up dataset
    dataset = dataset.fill_up(bucket_batch_sizes)
    indices = data_io.get_batch_indices(dataset, bucket_batch_sizes=bucket_batch_sizes)
    all_bucket_indices = set(list(range(len(dataset))))
    computed_bucket_indices = set([i for i, j in indices])

    assert not all_bucket_indices - computed_bucket_indices


get_parallel_bucket_tests = [([(10, 10), (20, 20), (30, 30), (40, 40), (50, 50)], 50, 50, 4, (50, 50)),
                             ([(10, 10), (20, 20), (30, 30), (40, 40), (50, 50)], 50, 10, 4, (50, 50)),
                             ([(10, 10), (20, 20), (30, 30), (40, 40), (50, 50)], 20, 10, 1, (20, 20)),
                             ([(10, 10)], 20, 10, None, None),
                             ([], 20, 10, None, None),
                             ([(10, 11)], 11, 10, None, None),
                             ([(11, 10)], 11, 10, 0, (11, 10))]


@pytest.mark.parametrize("buckets, source_length, target_length, expected_bucket_index, expected_bucket",
                         get_parallel_bucket_tests)
def test_get_parallel_bucket(buckets, source_length, target_length, expected_bucket_index, expected_bucket):
    bucket_index, bucket = data_io.get_parallel_bucket(buckets, source_length, target_length)
    assert bucket_index == expected_bucket_index
    assert bucket == expected_bucket


@pytest.mark.parametrize("sources, targets, expected_num_sents, expected_mean, expected_std",
                         [([[[1, 1, 1], [2, 2, 2], [3, 3, 3]]],
                           [[[1, 1, 1], [2, 2, 2], [3, 3, 3]]], 3, 1.0, 0.0),
                          ([[[1, 1], [2, 2], [3, 3]]],
                           [[[1, 1, 1], [2, 2, 2], [3, 3, 3]]], 3, 1.5, 0.0),
                          ([[[1, 1, 1], [2, 2], [3, 3, 3, 3, 3, 3, 3]]],
                           [[[1, 1, 1], [2], [3, 3, 3]]], 2, 0.75, 0.25)])
def test_calculate_length_statistics(sources, targets, expected_num_sents, expected_mean, expected_std):
    length_statistics = data_io.calculate_length_statistics(sources, targets, 5, 5)
    assert len(sources[0]) == len(targets[0])
    assert length_statistics.num_sents == expected_num_sents
    assert np.isclose(length_statistics.length_ratio_mean, expected_mean)
    assert np.isclose(length_statistics.length_ratio_std, expected_std)


@pytest.mark.parametrize("sources, targets",
                         [
                             ([[[1, 1, 1], [2, 2, 2], [3, 3, 3]],
                               [[1, 1, 1], [2, 2], [3, 3, 3]]],
                              [[[1, 1, 1], [2, 2, 2], [3, 3, 3]]])
                         ])
def test_non_parallel_calculate_length_statistics(sources, targets):
    with pytest.raises(SockeyeError):
        data_io.calculate_length_statistics(sources, targets, 5, 5)


def test_get_training_data_iters():
    from sockeye.test_utils import tmp_digits_dataset

    train_line_count = 100
    train_line_count_empty = 0
    train_max_length = 30
    dev_line_count = 20
    dev_max_length = 30
    expected_mean = 1.0
    expected_std = 0.0
    test_line_count = 20
    test_line_count_empty = 0
    test_max_length = 30
    batch_size = 5
    num_source_factors = num_target_factors = 1
    with tmp_digits_dataset("tmp_corpus",
                            train_line_count, train_line_count_empty, train_max_length - C.SPACE_FOR_XOS,
                            dev_line_count, dev_max_length - C.SPACE_FOR_XOS,
                            test_line_count, test_line_count_empty,
                            test_max_length - C.SPACE_FOR_XOS) as data:
        # tmp common vocab
        vcb = vocab.build_from_paths([data['train_source'], data['train_target']])

        train_iter, val_iter, config_data, data_info = data_io.get_training_data_iters(
            sources=[data['train_source']],
            targets=[data['train_target']],
            validation_sources=[data['dev_source']],
            validation_targets=[data['dev_target']],
            source_vocabs=[vcb],
            target_vocabs=[vcb],
            source_vocab_paths=[None],
            target_vocab_paths=[None],
            shared_vocab=True,
            batch_size=batch_size,
            batch_type=C.BATCH_TYPE_SENTENCE,
            max_seq_len_source=train_max_length,
            max_seq_len_target=train_max_length,
            bucketing=True,
            bucket_width=10)
        assert isinstance(train_iter, data_io.ParallelSampleIter)
        assert isinstance(val_iter, data_io.ParallelSampleIter)
        assert isinstance(config_data, data_io.DataConfig)
        assert data_info.sources == [data['train_source']]
        assert data_info.targets == [data['train_target']]
        assert data_info.source_vocabs == [None]
        assert data_info.target_vocabs == [None]
        assert config_data.data_statistics.max_observed_len_source == train_max_length
        assert config_data.data_statistics.max_observed_len_target == train_max_length
        assert np.isclose(config_data.data_statistics.length_ratio_mean, expected_mean)
        assert np.isclose(config_data.data_statistics.length_ratio_std, expected_std)

        assert train_iter.batch_size == batch_size
        assert val_iter.batch_size == batch_size

        # test some batches
        bos_id = vcb[C.BOS_SYMBOL]
        eos_id = vcb[C.EOS_SYMBOL]
        expected_first_target_symbols = torch.full((batch_size, 1), bos_id, dtype=torch.int32)
        for epoch in range(2):
            while train_iter.iter_next():
                batch = train_iter.next()
                assert isinstance(batch, data_io.Batch)
                source = batch.source
                target = batch.target
                label = batch.labels[C.TARGET_LABEL_NAME]  # TODO: still 2-shape: (batch, length)
                length_ratio_label = batch.labels[C.LENRATIO_LABEL_NAME]
                assert source.shape[0] == target.shape[0] == label.shape[0] == batch_size
                assert source.shape[2] == target.shape[2] == num_source_factors == num_target_factors
                # target first symbol should be BOS
                # each source sequence contains one EOS symbol
                assert torch.sum(source == eos_id) == batch_size
                assert torch.equal(target[:, 0], expected_first_target_symbols)
                # label first symbol should be 2nd target symbol
                assert torch.equal(label[:, 0], target[:, 1, 0])
                # each label sequence contains one EOS symbol
                assert torch.sum(label == eos_id) == batch_size
            train_iter.reset()


def _data_batches_equal(db1: data_io.Batch, db2: data_io.Batch) -> bool:
    equal = True
    equal = equal and torch.allclose(db1.source, db2.source)
    equal = equal and torch.allclose(db1.source_length, db2.source_length)
    equal = equal and torch.allclose(db1.target, db2.target)
    equal = equal and torch.allclose(db1.target_length, db2.target_length)
    equal = equal and db1.labels.keys() == db2.labels.keys()
    equal = equal and db1.samples == db2.samples
    equal = equal and db1.tokens == db2.tokens
    return equal


def test_parallel_sample_iter():
    batch_size = 2
    buckets = data_io.define_parallel_buckets(100, 100, 10, True, 1.0)
    # The first bucket is going to be empty:
    bucket_counts = [0] + [None] * (len(buckets) - 1)
    bucket_batch_sizes = data_io.define_bucket_batch_sizes(buckets,
                                                           batch_size,
                                                           batch_type=C.BATCH_TYPE_SENTENCE,
                                                           data_target_average_len=[None] * len(buckets))

    dataset = data_io.ParallelDataSet(*_get_random_bucketed_data(buckets, min_count=0, max_count=5,
                                                                 bucket_counts=bucket_counts))
    it = data_io.ParallelSampleIter(dataset, buckets, batch_size, bucket_batch_sizes)

    with TemporaryDirectory() as work_dir:
        # Test 1
        it.next()
        expected_batch = it.next()

        fname = os.path.join(work_dir, "saved_iter")
        it.save_state(fname)

        it_loaded = data_io.ParallelSampleIter(dataset, buckets, batch_size, bucket_batch_sizes)
        it_loaded.reset()
        it_loaded.load_state(fname)
        loaded_batch = it_loaded.next()
        assert _data_batches_equal(expected_batch, loaded_batch)

        # Test 2
        it.reset()
        expected_batch = it.next()
        it.save_state(fname)

        it_loaded = data_io.ParallelSampleIter(dataset, buckets, batch_size, bucket_batch_sizes)
        it_loaded.reset()
        it_loaded.load_state(fname)

        loaded_batch = it_loaded.next()
        assert _data_batches_equal(expected_batch, loaded_batch)

        # Test 3
        it.reset()
        expected_batch = it.next()
        it.save_state(fname)
        it_loaded = data_io.ParallelSampleIter(dataset, buckets, batch_size, bucket_batch_sizes)
        it_loaded.reset()
        it_loaded.load_state(fname)

        loaded_batch = it_loaded.next()
        assert _data_batches_equal(expected_batch, loaded_batch)

        while it.iter_next():
            it.next()
            it_loaded.next()
        assert not it_loaded.iter_next()


def test_sharded_parallel_sample_iter():
    batch_size = 2
    buckets = data_io.define_parallel_buckets(100, 100, 10, True, 1.0)
    # The first bucket is going to be empty:
    bucket_counts = [0] + [None] * (len(buckets) - 1)
    bucket_batch_sizes = data_io.define_bucket_batch_sizes(buckets,
                                                           batch_size,
                                                           batch_type=C.BATCH_TYPE_SENTENCE,
                                                           data_target_average_len=[None] * len(buckets))

    dataset1 = data_io.ParallelDataSet(*_get_random_bucketed_data(buckets, min_count=0, max_count=5,
                                                                  bucket_counts=bucket_counts))
    dataset2 = data_io.ParallelDataSet(*_get_random_bucketed_data(buckets, min_count=0, max_count=5,
                                                                  bucket_counts=bucket_counts))

    with TemporaryDirectory() as work_dir:
        shard1_fname = os.path.join(work_dir, 'shard1')
        shard2_fname = os.path.join(work_dir, 'shard2')
        dataset1.save(shard1_fname)
        dataset2.save(shard2_fname)
        shard_fnames = [shard1_fname, shard2_fname]

        it = data_io.ShardedParallelSampleIter(shard_fnames, buckets, batch_size, bucket_batch_sizes)

        # Test 1
        it.next()
        expected_batch = it.next()

        fname = os.path.join(work_dir, "saved_iter")
        it.save_state(fname)

        it_loaded = data_io.ShardedParallelSampleIter(shard_fnames, buckets, batch_size, bucket_batch_sizes)
        it_loaded.reset()
        it_loaded.load_state(fname)
        loaded_batch = it_loaded.next()
        assert _data_batches_equal(expected_batch, loaded_batch)

        # Test 2
        it.reset()
        expected_batch = it.next()
        it.save_state(fname)

        it_loaded = data_io.ShardedParallelSampleIter(shard_fnames, buckets, batch_size, bucket_batch_sizes)
        it_loaded.reset()
        it_loaded.load_state(fname)

        loaded_batch = it_loaded.next()
        assert _data_batches_equal(expected_batch, loaded_batch)

        # Test 3
        it.reset()
        expected_batch = it.next()
        it.save_state(fname)
        it_loaded = data_io.ShardedParallelSampleIter(shard_fnames, buckets, batch_size, bucket_batch_sizes)
        it_loaded.reset()
        it_loaded.load_state(fname)

        loaded_batch = it_loaded.next()
        assert _data_batches_equal(expected_batch, loaded_batch)

        while it.iter_next():
            it.next()
            it_loaded.next()
        assert not it_loaded.iter_next()


def test_sharded_parallel_sample_iter_num_batches():
    num_shards = 2
    batch_size = 2
    num_batches_per_bucket = 10
    buckets = data_io.define_parallel_buckets(100, 100, 10, True, 1.0)
    bucket_counts = [batch_size * num_batches_per_bucket for _ in buckets]
    num_batches_per_shard = num_batches_per_bucket * len(buckets)
    num_batches = num_shards * num_batches_per_shard
    bucket_batch_sizes = data_io.define_bucket_batch_sizes(buckets,
                                                           batch_size,
                                                           batch_type=C.BATCH_TYPE_SENTENCE,
                                                           data_target_average_len=[None] * len(buckets))

    dataset1 = data_io.ParallelDataSet(*_get_random_bucketed_data(buckets, min_count=0, max_count=5,
                                                                  bucket_counts=bucket_counts))
    dataset2 = data_io.ParallelDataSet(*_get_random_bucketed_data(buckets, min_count=0, max_count=5,
                                                                  bucket_counts=bucket_counts))
    with TemporaryDirectory() as work_dir:
        shard1_fname = os.path.join(work_dir, 'shard1')
        shard2_fname = os.path.join(work_dir, 'shard2')
        dataset1.save(shard1_fname)
        dataset2.save(shard2_fname)
        shard_fnames = [shard1_fname, shard2_fname]

        it = data_io.ShardedParallelSampleIter(shard_fnames, buckets, batch_size, bucket_batch_sizes)

        num_batches_seen = 0
        while it.iter_next():
            it.next()
            num_batches_seen += 1
        assert num_batches_seen == num_batches


def test_sharded_and_parallel_iter_same_num_batches():
    """ Tests that a sharded data iterator with just a single shard produces as many shards as an iterator directly
    using the same dataset. """
    batch_size = 2
    num_batches_per_bucket = 10
    buckets = data_io.define_parallel_buckets(100, 100, 10, True, 1.0)
    bucket_counts = [batch_size * num_batches_per_bucket for _ in buckets]
    num_batches = num_batches_per_bucket * len(buckets)
    bucket_batch_sizes = data_io.define_bucket_batch_sizes(buckets,
                                                           batch_size,
                                                           batch_type=C.BATCH_TYPE_SENTENCE,
                                                           data_target_average_len=[None] * len(buckets))

    dataset = data_io.ParallelDataSet(*_get_random_bucketed_data(buckets, min_count=0, max_count=5,
                                                                 bucket_counts=bucket_counts))

    with TemporaryDirectory() as work_dir:
        shard_fname = os.path.join(work_dir, 'shard1')
        dataset.save(shard_fname)
        shard_fnames = [shard_fname]

        it_sharded = data_io.ShardedParallelSampleIter(shard_fnames, buckets, batch_size, bucket_batch_sizes)

        it_parallel = data_io.ParallelSampleIter(dataset, buckets, batch_size, bucket_batch_sizes)

        num_batches_seen = 0
        while it_parallel.iter_next():
            assert it_sharded.iter_next()
            it_parallel.next()
            it_sharded.next()
            num_batches_seen += 1
        assert num_batches_seen == num_batches

        print("Resetting...")
        it_sharded.reset()
        it_parallel.reset()

        num_batches_seen = 0
        while it_parallel.iter_next():
            assert it_sharded.iter_next()
            it_parallel.next()
            it_sharded.next()

            num_batches_seen += 1

        assert num_batches_seen == num_batches


def test_create_target_and_shifted_label_sequences():
    target_and_label = torch.tensor([[C.BOS_ID, 4, 17, 35, 12, C.EOS_ID, C.PAD_ID, C.PAD_ID],
                                     [C.BOS_ID, 15, 23, 23, 77, 55, 22, C.EOS_ID],
                                     [C.BOS_ID, 4, C.EOS_ID, C.PAD_ID, C.PAD_ID, C.PAD_ID, C.PAD_ID, C.PAD_ID]])
    expected_label = torch.tensor([[4, 17, 35, 12, C.EOS_ID, C.PAD_ID, C.PAD_ID],
                                   [15, 23, 23, 77, 55, 22, C.EOS_ID],
                                   [4, C.EOS_ID, C.PAD_ID, C.PAD_ID, C.PAD_ID, C.PAD_ID, C.PAD_ID]]).unsqueeze(2)
    expected_target = torch.tensor([[C.BOS_ID, 4, 17, 35, 12, C.PAD_ID, C.PAD_ID],
                                    [C.BOS_ID, 15, 23, 23, 77, 55, 22],
                                    [C.BOS_ID, 4, C.PAD_ID, C.PAD_ID, C.PAD_ID, C.PAD_ID, C.PAD_ID]]).unsqueeze(2)
    target_and_label = torch.unsqueeze(target_and_label, dim=2)
    expected_lengths = torch.tensor([5, 7, 2])

    target, label = data_io.create_target_and_shifted_label_sequences(target_and_label)

    assert target.shape[0] == label.shape[0] == target_and_label.shape[0]
    assert target.shape[1] == label.shape[1] == target_and_label.shape[1] - 1
    assert torch.allclose(target, expected_target)
    assert torch.allclose(label, expected_label)
    lengths = (target != C.PAD_ID).sum(dim=1).squeeze()
    assert torch.allclose(lengths, expected_lengths)
