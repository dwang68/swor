import logging
import time

import utils, sampling_utils
import numpy as np
from decoding.core import Decoder, PartialHypothesis


class ReferenceDecoder(Decoder):
    
    name = "reference"
    def __init__(self, decoder_args):
        """Creates a new reference decoder instance. The following values are
        fetched from `decoder_args`:
        
        Args:
            decoder_args (object): Decoder configuration passed through
                                   from the configuration API.
        """
        super(ReferenceDecoder, self).__init__(decoder_args)
        
    def decode(self, src_sentence, trgt_sentence):
        self.trgt_sentence = trgt_sentence + [utils.EOS_ID]
        self.initialize_predictor(src_sentence)

        hypo = PartialHypothesis(self.get_predictor_states())
        self.set_predictor_states(hypo.predictor_states)
        while hypo.get_last_word() != utils.EOS_ID:
            self._expand_hypo(hypo)
                
        hypo.score = self.get_adjusted_score(hypo)
        self.add_full_hypo(hypo.generate_full_hypothesis())
        return self.get_full_hypos_sorted()


    def _expand_hypo(self,hypo):

        next_word = self.trgt_sentence[len(hypo.trgt_sentence)]
        ids, posterior, _ = self.apply_predictor()
        ind = utils.binary_search(ids, k)

        #max_score = utils.max_(posterior)
        hypo.score += posterior[ind] 
        hypo.score_breakdown.append(posterior[ind])
        hypo.trgt_sentence += [next_word]
        self.consume(next_word)
                
