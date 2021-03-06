#!/usr/bin/env python
# coding: utf-8

# inception_resnet_v2_inputs.py

"""
Inception-ResNet V2 model for Keras

The Inception-Resnet A, B and C blocks are 35 x 35, 17 x 17 and 8 x 8 respectively in the gride size. 
Please note the filters in the joint convoluation for A B and C blocks are respectively 384, 1154 and 
2048. It is a variant without an auxiliary classifier. Please run the 

$ python inception_resnet_v2_inputs.py

If users want to run the model, please run the script of Inceptin_v4_func.py. Since it is abstract, 
we do not set the argument of the weights that need to be downloaded from designated weblink. 

The original model naming and structure follows TF-slim implementation (which has some additional
layers and different number of filters from the original arXiv paper):
https://github.com/tensorflow/models/blob/master/slim/nets/inception_resnet_v2.py

Make the the necessary changes to adapt to the environment of TensorFlow 2.3, Keras 2.4.3, CUDA Toolkit 
11.0, cuDNN 8.0.1 and CUDA 450.57. In addition, write the new lines of code to replace the deprecated 
code.  

Environment: 
Ubuntu 18.04 
TensorFlow 2.3
Keras 2.4.3
CUDA Toolkit 11.0, 
cuDNN 8.0.1
CUDA 450.57.

Pre-trained ImageNet weights are also converted from TF-slim, which can be found in:
https://github.com/tensorflow/models/tree/master/slim#pre-trained-models

# Reference
- Inception-v4, Inception-ResNet and the Impact ofResidual Connections on Learning
- https://arxiv.org/abs/1602.07261)
"""

import numpy as np
import tensorflow as tf 
from keras.models import Model

from keras import backend as K
from keras.preprocessing import image
from keras.layers import Conv2D, Dense, Input, Lambda, Activation, Concatenate, BatchNormalization, \
    MaxPooling2D, AveragePooling2D, GlobalAveragePooling2D, GlobalMaxPooling2D

from keras.utils.data_utils import get_file
from imagenet_utils import _obtain_input_shape
from keras.engine.topology import get_source_inputs
from keras.applications.imagenet_utils import decode_predictions


# Set up the GPU to avoid the runtime error: Could not create cuDNN handle...
gpus = tf.config.experimental.list_physical_devices('GPU')
for gpu in gpus:
    tf.config.experimental.set_memory_growth(gpu, True)


# Assume users have already downloaded the Inception v4 weights 
WEIGHTS_PATH = '/home/mike/keras_dnn_models/inception_resnet_v2_weights_tf_dim_ordering_tf_kernels.h5'
WEIGHTS_PATH_NO_TOP = '/home/mike/keras_dnn_models/inception_resnet_v2_weights_tf_dim_ordering_tf_kernels_notop.h5'


def conv2d_bn(x, filters, kernel_size, strides=1, padding='same', activation='relu', 
              use_bias=False, name=None):
    x = Conv2D(filters, kernel_size, strides=strides, padding=padding, 
               use_bias=use_bias, name=name)(x)
    if not use_bias:
        bn_axis = 3 if K.image_data_format() == 'channels_last' else 1
        bn_name = None if name is None else name + '_bn'
        x = BatchNormalization(axis=bn_axis, scale=False, name=bn_name)(x)
    if activation is not None:
        ac_name = None if name is None else name + '_ac'
        x = Activation(activation, name=ac_name)(x)

    return x


def inception_stem(input):
    # Stem block: 35 x 35 x 192
    x = conv2d_bn(input, 32, 3, strides=2, padding='valid')
    x = conv2d_bn(x, 32, 3, padding='valid')
    x = conv2d_bn(x, 64, 3)
    x = MaxPooling2D(3, strides=2)(x)
    x = conv2d_bn(x, 80, 1, padding='valid')
    x = conv2d_bn(x, 192, 3, padding='valid')
    x = MaxPooling2D(3, strides=2)(x)

    return x 


def inception_a(input):
    # Inception-A block: 35 x 35 x 320
    branch_11 = conv2d_bn(input, 96, 1)

    branch_12 = conv2d_bn(input, 48, 1)
    branch_22 = conv2d_bn(branch_12, 64, 5)

    branch_13 = conv2d_bn(input, 64, 1)
    branch_23 = conv2d_bn(branch_13, 96, 3)
    branch_33 = conv2d_bn(branch_23, 96, 3)

    branch_14 = AveragePooling2D(pool_size=(3,3), strides=1, padding='same')(input)
    branch_24 = conv2d_bn(branch_14, 64, 1)

    branches = [branch_11, branch_22, branch_33, branch_24]

    x = Concatenate(axis=3, name='mixed_5b')(branches)

    return x 


def inception_resnet_block(input, scale, block_type, block_idx, activation='relu'):
    # Adds an Inception-ResNet block.
    if block_type == 'block35':

        branch_11 = conv2d_bn(input, 32, 1)

        branch_12 = conv2d_bn(input, 32, 1)
        branch_22 = conv2d_bn(branch_12, 32, 3)

        branch_13 = conv2d_bn(input, 32, 1)
        branch_23 = conv2d_bn(branch_13, 48, 3)
        branch_33 = conv2d_bn(branch_23, 64, 3)

        branches = [branch_11, branch_22, branch_33]

    elif block_type == 'block17':

        branch_11 = conv2d_bn(input, 192, 1)

        branch_12 = conv2d_bn(input, 128, 1)
        branch_22 = conv2d_bn(branch_12, 160, [1, 7])
        branch_32 = conv2d_bn(branch_22, 192, [7, 1])

        branches = [branch_11, branch_32]

    elif block_type == 'block8':

        branch_11 = conv2d_bn(input, 192, 1)

        branch_12 = conv2d_bn(input, 192, 1)
        branch_22 = conv2d_bn(branch_12, 224, [1, 3])
        branch_32 = conv2d_bn(branch_22, 256, [3, 1])

        branches = [branch_11, branch_32]

    else:

        raise ValueError('Unknown Inception-ResNet block type. '
                         'Expects "block35", "block17" or "block8", '
                         'but got: ' + str(block_type))

    block_name = block_type + '_' + str(block_idx)

    mix = Concatenate(axis=3, name=block_name + '_mixed')(branches)
    up = conv2d_bn(mix, K.int_shape(input)[3], kernel_size=(1,1), activation=None, 
                   use_bias=True, name=block_name + '_conv')

    up = Lambda(lambda inputs, scale: inputs[0]+inputs[1]*scale, 
                output_shape=K.int_shape(input)[1:], 
                arguments={'scale': scale}, 
                name=block_name)([input, up])

    if activation is not None:
        x = Activation(activation, name=block_name + '_ac')(up)

    return x

def reduction_a(input):
    # Mixed 6a (Reduction-A block): 17 x 17
    branch_11 = conv2d_bn(input, 384, 3, strides=2, padding='valid')

    branch_12 = conv2d_bn(input, 256, 1)
    branch_22 = conv2d_bn(branch_12, 256, 3)
    branch_32 = conv2d_bn(branch_22, 384, 3, strides=2, padding='valid')

    branch_13 = MaxPooling2D(pool_size=(3,3), strides=2, padding='valid')(input)

    branches = [branch_11, branch_32, branch_13]

    x = Concatenate(axis=3, name='mixed_6a')(branches)

    return x 


def reduction_b(input):
    # Mixed 7a (Reduction-B block): 8 x 8 
    branch_11 = conv2d_bn(input, 256, 1)
    branch_21 = conv2d_bn(branch_11, 384, 3, strides=2, padding='valid')

    branch_12 = conv2d_bn(input, 256, 1)
    branch_22 = conv2d_bn(branch_12, 288, 3, strides=2, padding='valid')

    branch_13 = conv2d_bn(input, 256, 1)
    branch_23 = conv2d_bn(branch_13, 288, 3)
    branch_33 = conv2d_bn(branch_23, 320, 3, strides=2, padding='valid')

    branch_14 = MaxPooling2D(pool_size=(3,3), strides=2, padding='valid')(input)

    branches = [branch_21, branch_22, branch_33, branch_14]

    x = Concatenate(axis=3, name='mixed_7a')(branches)

    return x 


def inception_resnet_v2(include_top=True, weights='imagenet', input_tensor=None,
                        input_shape=None, pooling=None, classes=1000):
    # Determine proper input shape (-K.image_data_format())
    input_shape = _obtain_input_shape(input_shape, default_size=299, min_size=139, data_format=None,
                                      require_flatten=include_top, weights=weights)

    # Initizate a 3D shape into a 4D tensor with a batch. If no batch size, 
    # it is defaulted as None.
    inputs = Input(shape=input_shape)

    # Call the function of inception_stem()
    x = inception_stem(inputs)

    # Call the function of inception_a
    x = inception_a(x)

    # 10x block35 (Inception-ResNet-A block): 35 x 35 x 320
    for block_idx in range(1, 11):
        x = inception_resnet_block(x, scale=0.17, block_type='block35', block_idx=block_idx)

    # Reduction-A Block 
    x = reduction_a(x)

    # 20x block17 (Inception-ResNet-B block): 17 x 17 x 1088
    for block_idx in range(1, 21):
        x = inception_resnet_block(x, scale=0.1, block_type='block17', block_idx=block_idx)

    # Reduction-B Block 
    x = reduction_b(x)

    # 10x block8 (Inception-ResNet-C block): 8 x 8 x 2080
    for block_idx in range(1, 11):
        x = inception_resnet_block(x, scale=0.2, block_type='block8', block_idx=block_idx)

    # Final convolution block: 8 x 8 x 1536
    x = conv2d_bn(x, 1536, 1, name='conv_7b')

    if include_top:
        # Classification block
        x = GlobalAveragePooling2D(name='avg_pool')(x)
        x = Dense(classes, activation='softmax', name='predictions')(x)
    else:
        if pooling == 'avg':
            x = GlobalAveragePooling2D()(x)
        elif pooling == 'max':
            x = GlobalMaxPooling2D()(x)

    # Create model
    model = Model(inputs, x, name='inception_resnet_v2')

    # load weights
    if weights == 'imagenet':
        if include_top:
            weights_path = WEIGHTS_PATH
        else:
            weights_path = WEIGHTS_PATH_NO_TOP
        # -model.load_weights(weights_path, by_name=True)
        model.load_weights(weights_path)

    return model


def preprocess_input(x):
    x = image.img_to_array(x)
    x = np.expand_dims(x, axis=0)
    x = np.divide(x, 255.0)
    x = np.subtract(x, 0.5)
    output = np.multiply(x, 2.0)

    return output 


if __name__ == '__main__':

    input_shape = (229,299,3)

    model = inception_resnet_v2(input_shape)

    model.summary()

    img_path = '/home/mike/Documents/keras_inception_resnet_v2/elephant.jpg'
    img = image.load_img(img_path, target_size=(299, 299))
    output = preprocess_input(img)

    preds = model.predict(output)
    print('Predicted:', decode_predictions(preds))