# Copyright 2022 Amazon.com, Inc. or its affiliates. All Rights Reserved.
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

import argparse
import gc
import logging
import os
import shutil

from . import constants as C
from . import model

try:
    import deepspeed
    import deepspeed.utils.zero_to_fp32
except ImportError:
    pass


logger = logging.getLogger(__name__)


def convert_checkpoint_to_params(model_config_fname: str, checkpoint_dirname: str, params_fname: str):
    # Create a temporary SockeyeModel
    model_config = model.SockeyeModel.load_config(model_config_fname)
    sockeye_model = model.SockeyeModel(model_config)
    # Gather the float32 params on CPU
    state_dict = deepspeed.utils.zero_to_fp32.get_fp32_state_dict_from_zero_checkpoint(checkpoint_dirname)
    # Strip the first prefix from each param name to match the SockeyeModel
    # Ex: 'model.encoder.layers...' -> 'encoder.layers...'
    state_dict = {name[name.find('.') + 1:]: param for (name, param) in state_dict.items()}
    # Load the float32 params. Use non-strict mode because shared and constant
    # params are not included in the DeepSpeed-generated state dict.
    sockeye_model.load_state_dict(state_dict, strict=False)
    # Save the float32 params to disk
    sockeye_model.save_parameters(params_fname)
    # Cleanup
    del sockeye_model
    gc.collect()


def convert_model_checkpoints(model_dirname: str, keep_deepspeed: bool = False):
    model_config_fname = os.path.join(model_dirname, C.CONFIG_NAME)
    # Find and convert params.00000, etc.
    for fname in os.listdir(model_dirname):
        if fname.startswith(C.PARAMS_PREFIX) and fname[len(C.PARAMS_PREFIX):].isdigit():
            params_fname = os.path.join(model_dirname, fname)
            if os.path.isdir(params_fname):
                logger.info(f'Converting checkpoint {params_fname}')
                # Move directory checkpoint to e.g., params.00000.ds
                checkpoint_dirname = params_fname + '.ds'
                shutil.move(params_fname, checkpoint_dirname)
                # Create params file for directory checkpoint
                convert_checkpoint_to_params(model_config_fname, checkpoint_dirname, params_fname)
                if not keep_deepspeed:
                    shutil.rmtree(checkpoint_dirname)
    # Update params.best
    params_best_fname = os.path.join(model_dirname, C.PARAMS_BEST_NAME)
    if os.path.exists(params_best_fname) and os.path.islink(params_best_fname):
        logger.info(f'Updating {params_best_fname}')
        params_best_target = os.readlink(params_best_fname)
        os.remove(params_best_fname)
        os.symlink(params_best_target, params_best_fname)


def main():
    params = argparse.ArgumentParser(
        description="Convert DeepSpeed checkpoints to regular parameter files in a Sockeye model directory.")
    params.add_argument('--model', '-m',
                        required=True,
                        help='Model directory containing DeepSpeed checkpoints.')
    params.add_argument('--keep-deepspeed', '-k',
                        action='store_true',
                        help='Keep DeepSpeed checkpoints (renamed e.g., params.00000.ds).')
    args = params.parse_args()
    convert_model_checkpoints(args.model, keep_deepspeed=args.keep_deepspeed)


if __name__ == "__main__":
    main()
