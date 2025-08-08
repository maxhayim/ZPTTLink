import logging
logger = logging.getLogger("ZPTTLink")

def init(input_device, output_device):
    logger.info(f"Audio input: {input_device}")
    logger.info(f"Audio output: {output_device}")
    # TODO: Integrate Virtual Audio Cable routing here
