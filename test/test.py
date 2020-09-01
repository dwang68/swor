# -*- coding: utf-8 -*-
# coding=utf-8
# Copyright 2019 The SGNMT Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""This module is the bridge between the command line configuration of
the decode.py script and the SGNMT software architecture consisting of
decoders, predictor, and output handlers. A common use case is to call
`create_decoder()` first, which reads the SGNMT configuration and loads
the right predictor and decoding strategy with the right arguments.
The actual decoding is implemented in `do_decode()`. See `decode.py`
to learn how to use this module.
"""

import logging
import codecs
import sys
import time
import traceback
import os
import uuid
import numpy as np
import random
import string
import collections

import utils
import scipy
import sampling_utils
import decoding

from test.dummy_predictor import DummyPredictor
from ui import get_args

random.seed(0)
args = None
"""This variable is set to the global configuration when 
base_init().
"""

def base_init(new_args):
    """This function should be called before accessing any other
    function in this module. It initializes the `args` variable on 
    which all the create_* factory functions rely on as configuration
    object, and it sets up global function pointers and variables for
    basic things like the indexing scheme, logging verbosity, etc.

    Args:
        new_args: Configuration object from the argument parser.
    """
    global args
    args = new_args
    # UTF-8 support
    if sys.version_info < (3, 0):
        sys.stderr = codecs.getwriter('UTF-8')(sys.stderr)
        sys.stdout = codecs.getwriter('UTF-8')(sys.stdout)
        sys.stdin = codecs.getreader('UTF-8')(sys.stdin)
        logging.warn("SGNMT is tested with Python 3, but you are using "
                     "Python 2. Expect the unexpected or switch to >3.5.")
    # Set up logger
    logger = logging.getLogger(__name__)
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s')
    logging.getLogger().setLevel(logging.INFO)
    if args.verbosity == 'debug':
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.verbosity == 'info':
        logging.getLogger().setLevel(logging.INFO)
    elif args.verbosity == 'warn':
        logging.getLogger().setLevel(logging.WARN)
    elif args.verbosity == 'error':
        logging.getLogger().setLevel(logging.ERROR)
    # Set reserved word IDs
    utils.switch_to_fairseq_indexing()

def add_predictor(decoder):
    """Adds all enabled predictor to the ``decoder``. This function 
    makes heavy use of the global ``args`` which contains the
    SGNMT configuration. Particularly, it reads out ``args.predictor``
    and adds appropriate instances to ``decoder``.
    TODO: Refactor this method as it is waaaay tooooo looong
    
    Args:
        decoder (Decoder):  Decoding strategy, see ``create_decoder()``.
            This method will add predictor to this instance with
            ``add_predictor()``
    """
    
    pred_weight = 1.0
    p = DummyPredictor(vocab_size=20)
    decoder.add_predictor("dummy", p)

def create_decoder():
    """Creates the ``Decoder`` instance. This specifies the search 
    strategy used to traverse the space spanned by the predictors. This
    method relies on the global ``args`` variable.
    
    TODO: Refactor to avoid long argument lists
    
    Returns:
        Decoder. Instance of the search strategy
    """
    # Create decoder instance and add predictors
    
    try:
        decoder = decoding.DECODER_REGISTRY[args.decoder](args)
    except Exception as e:
        logging.fatal("An %s has occurred while initializing the decoder: %s"
                      " Stack trace: %s" % (sys.exc_info()[0],
                                            e,
                                            traceback.format_exc()))
        sys.exit("Could not initialize decoder.")
        
    add_predictor(decoder)
    return decoder


def _generate_dummy_hypo():
    return decoding.core.Hypothesis([utils.UNK_ID], 0.0, [0.0]) 

def randomString(stringLength=5):
    letters = string.ascii_lowercase
    return [random.choice(letters) for i in range(stringLength)]

def do_decode(decoder, 
              output_handlers, 
              src_sentences,
              trgt_sentences=None,
              test_str_length=5,
              num_log=1):
    """This method contains the main decoding loop. It iterates through
    ``src_sentences`` and applies ``decoder.decode()`` to each of them.
    At the end, it calls the output handlers to create output files.
    
    Args:
        decoder (Decoder):  Current decoder instance
        output_handlers (list):  List of output handlers, see
                                 ``create_output_handlers()``
        src_sentences (list):  A list of strings. The strings are the
                               source sentences with word indices to 
                               translate (e.g. '1 123 432 2')
    """
    if not decoder.has_predictor():
        logging.fatal("Terminated due to an error in the "
                      "predictor configuration.")
        return
    all_hypos = []
    
    start_time = time.time()
    logging.info("Start time: %s" % start_time)
    src_sentences = [randomString(test_str_length) for i in range(10)]
    for sen_idx, src in enumerate(src_sentences):
        decoder.set_current_sen_id(sen_idx)
        logging.info("Next sentence (ID: %d): %s" % (sen_idx + 1, ''.join(src)))
        decoder.apply_predictor_count = 0
        start_hypo_time = time.time()
        hypos = decoder.decode(src)
        all_hypos.append(hypos)
        if not hypos:
            logging.error("No translation found for ID %d!" % (sen_idx+1))
            logging.info("Stats (ID: %d): score=<not-found> "
                     "num_expansions=%d "
                     "time=%.2f" % (sen_idx+1,
                                    decoder.apply_predictor_count,
                                    time.time() - start_hypo_time))
            hypos = [_generate_dummy_hypo()]
        
        for logged_hypo in sorted(hypos, reverse=True)[:num_log]:
            logging.info("Decoded (ID: %d): %s" % (
                    sen_idx+1,
                    logged_hypo.trgt_sentence))
            logging.info("Stats (ID: %d): score=%f "
                        "inc=%f "
                         "num_expansions=%d "
                         "time=%.2f " 
                         "perplexity=%.2f"% (sen_idx+1,
                                        logged_hypo.total_score,
                                        logged_hypo.base_score,
                                        decoder.apply_predictor_count,
                                        time.time() - start_hypo_time,
                                        utils.perplexity(logged_hypo.score_breakdown)))
    return src_sentences, all_hypos


def do_decode_swor(decoder, 
              output_handlers, 
              src_sentences,
              trgt_sentences=None,
              num_log=1):
    args.decoder = "inclusion"
    inc_decoder = create_decoder()
    
    src_sentences, all_hypos = do_decode(decoder, output_handlers, src_sentences, trgt_sentences, num_log=num_log)
    all_trgt_sens = [[tuple(h.trgt_sentence) for h in hypos] for hypos in all_hypos]
    for s, hypos in zip(src_sentences, all_trgt_sens):
        if len(hypos) != len(set(hypos)):
            logging.error("Not unique set for sentence %s; found %d duplicates." % (str(s), len(hypos) - len(set(hypos))))
        if hypos:
            for i in range(5):
                print(inc_decoder.decode(s,list(hypos[-1]), seed=i))
            print('----')
    for hypos in all_hypos:
        for h in hypos:
            if h.total_score > sum(h.score_breakdown) and not decoder.gumbel:
                logging.error("Computation error. Adjusted score greater than original score for sentence %s" % str(s))

def test_cp_decode(decoder, 
              output_handlers, 
              src_sentences,
              trgt_sentences=None,
              test_str_length=5,
              num_log=1):
    """This method contains the main decoding loop. It iterates through
    ``src_sentences`` and applies ``decoder.decode()`` to each of them.
    At the end, it calls the output handlers to create output files.
    
    Args:
        decoder (Decoder):  Current decoder instance
        output_handlers (list):  List of output handlers, see
                                 ``create_output_handlers()``
        src_sentences (list):  A list of strings. The strings are the
                               source sentences with word indices to 
                               translate (e.g. '1 123 432 2')
    """
    if not decoder.has_predictor():
        logging.fatal("Terminated due to an error in the "
                      "predictor configuration.")
        return
    all_hypos = []
    
    start_time = time.time()
    logging.info("Start time: %s" % start_time)
    src = randomString(test_str_length)

    counts = collections.defaultdict(int)
    stats = {}

    num_trials = 1000
    for sen_idx in range(num_trials):
        decoder.set_current_sen_id(sen_idx)
        logging.info("Next sentence (ID: %d): %s" % (sen_idx + 1, ''.join(src)))
        decoder.apply_predictors_count = 0
        start_hypo_time = time.time()
        hypos = decoder.decode(src, seed=sen_idx)
        all_hypos.append(hypos)
        if not hypos:
            logging.error("No translation found for ID %d!" % (sen_idx+1))
            logging.info("Stats (ID: %d): score=<not-found> "
                     "num_expansions=%d "
                     "time=%.2f" % (sen_idx+1,
                                    decoder.apply_predictor_count,
                                    time.time() - start_hypo_time))
            hypos = [_generate_dummy_hypo()]
        else:

            assert len(hypos) <= decoder.nbest

            for h in hypos:
                counts[tuple(h.trgt_sentence)] += 1
                stats[tuple(h.trgt_sentence)] = h.score_breakdown
            
            for logged_hypo in sorted(hypos, reverse=True)[:num_log]:
                logging.info("Decoded (ID: %d): %s" % (
                        sen_idx+1,
                        logged_hypo.trgt_sentence))
                logging.info("Stats (ID: %d): score=%f "
                            "inc=%f "
                             "num_expansions=%d "
                             "time=%.2f " 
                             "perplexity=%.2f"% (sen_idx+1,
                                            logged_hypo.total_score,
                                            logged_hypo.base_score,
                                            decoder.apply_predictors_count,
                                            time.time() - start_hypo_time,
                                            utils.perplexity(logged_hypo.score_breakdown)))
        
    args.decoder = "inclusion"
    inc_decoder = create_decoder()
    diffs1 = []
    for k,v in counts.items():
        #if v > 2:
            probs = []
            for i in range(50):
                probs.append(inc_decoder.decode(src,list(k), seed=i))
            # inv_inc_prob = utils.logsumexp(probs)
            # log_num_beams = utils.log_comb((decoder.nbest-1)**decoder.max_len, decoder.nbest - 1)
            # guess = np.exp(inv_inc_prob - log_num_beams - np.log(len(probs)))
            print(k)
            guess = np.exp(utils.logsumexp(probs) - np.log(len(probs)))
            print(guess, v/num_trials)
            #print(np.mean(probs[k]) - v/num_trials, np.mean(probs[k]), v/num_trials, np.exp(bprob[k]), np.exp(stats[k]), np.var(probs[k]))
            #print(probs)
            #print(stats[k])
            
            diffs1.append(abs( guess - v/num_trials))
    print(diffs1)
    print(np.mean(diffs1))
    return src_sentences


def test_utils():
    from arsenal.maths import assert_equal
    from scipy.special import binom

    for i in range(10):
        N = np.random.randint(2,50)
        k = np.random.randint(1,N)
        min_fac = min(N-k, k)
        # print(abs(np.exp(utils.log_comb(N,k)) - binom(N,k)))
        # print(3/(360*(min_fac)**3))
        # assert abs(np.exp(utils.log_comb(N,k)) - binom(N,k)) < 3/(12*(min_fac+1))

    for a,b in np.random.uniform(0, 10, size=(100, 2)):

        if a < b:
            a, b = b, a

        want = np.log(a-b)
        assert_equal(want, utils.log_minus(np.log(a), np.log(b)), 'log sub timv')
        assert_equal(want, utils.log_minus_old(np.log(a), np.log(b)), 'log sub clara')

        want = np.log(a+b)
        assert_equal(want, utils.log_add(np.log(a), np.log(b)), 'log add timv')
        assert_equal(want, utils.log_add_old(np.log(a), np.log(b)), 'log add clara')

    

def test_sampling():
    from arsenal.maths import assert_equal

    def partition_brute(lambdas,k):
        from itertools import combinations
        all_combs = list(combinations(lambdas, k))
        partition = [utils.prod(i) for i in all_combs]
        return sum(partition)

    for i in range(100):
        N = np.random.randint(2,20)
        k = np.random.randint(1,N)
        lambdas = np.random.uniform(size=N)
        log_lambdas = np.log(lambdas)
        
        elem_polynomial_partition = sampling_utils.elem_polynomials(lambdas, k)[k, len(lambdas)]
        log_elem_polynomial_partition = sampling_utils.log_elem_polynomials(log_lambdas, k)[k, len(lambdas)]
        brute_partition = partition_brute(lambdas,k)
        assert_equal(brute_partition, elem_polynomial_partition, 'standard elementary polynomial')
        assert_equal(np.log(brute_partition), log_elem_polynomial_partition, 'log elementary polynomial')

    for i in range(1):
        N = np.random.randint(2,20)
        k = np.random.randint(1,N)
        lambdas = np.random.uniform(size=N)
        log_lambdas = np.log(lambdas)
        a = [0]*N
        iters = 100000
        for i in range(iters):
            inds, _, inc_probs = sampling_utils.log_sample_k_dpp(log_lambdas, k, seed=i)
            for j in inds:
                a[j] += 1
        x = [i/iters for i in a]
        y = np.exp([min(0., l) for l in inc_probs])
        assert sum(abs(x-y))/len(x) < 0.01


args = get_args()
base_init(args)

if not args.decoder:
    test_sampling()
    test_utils()
    exit(0)

decoder = create_decoder()

if 'swor' in args.decoder or args.gumbel:
    if args.decoder == 'cp_swor':
        test_cp_decode(decoder, [], False, num_log=args.num_log)
    else:
        do_decode_swor(decoder, [], False, num_log=args.num_log)
else:
    if args.beam <= 0:
        logging.warn("Using beam size <= 0. Decoding may not terminate")
    do_decode(decoder, [], False, num_log=args.num_log)


