__author__ = 'Brian M Anderson'
# Created on 05/02/2022

import sys
import os.path
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import tensorflow as tf
import numpy as np
from tensorflow.python.framework import tensor_shape
from tensorflow.python.ops import array_ops
from tensorflow.python.ops import math_ops
from tensorflow.python.ops import control_flow_ops
from tensorflow.python.ops import random_ops
from tensorflow.python.framework import ops
from PlotScrollNumpyArrays.Plot_Scroll_Images import plot_scroll_Image, plt


def _check_keys_(input_features, keys):
    if type(keys) is list or type(keys) is tuple:
        for key in keys:
            assert key in input_features.keys(), 'Make sure the key you are referring to is present in the features, ' \
                                                 '{} was not found'.format(key)
    else:
        assert keys in input_features.keys(), 'Make sure the key you are referring to is present in the features, ' \
                                              '{} was not found'.format(keys)


class ImageProcessor(object):
    def parse(self, *args, **kwargs):
        return args, kwargs


class Decoder(object):
    def __init__(self, d_type_dict=None):
        self.d_type_dict = d_type_dict


class DecodeImagesAnnotations(Decoder):
    def parse(self, image_features, *args, **kwargs):
        all_keys = list(image_features.keys())
        is_modern = False
        for key in image_features.keys():
            if key.find('size') != -1:
                continue
            size_keys = [i for i in all_keys if i.find('size') != -1 and i.split('_size')[0] == key]  # All size keys
            size_keys.sort(key=lambda x: x.split('_')[-1])
            if size_keys:
                dtype = 'float'
                if key in self.d_type_dict:
                    dtype = self.d_type_dict[key]
                out_size = tuple([image_features[i] for i in size_keys])
                image_features[key] = tf.reshape(tf.io.decode_raw(image_features[key], out_type=dtype),
                                                 out_size)
                is_modern = True
        if not is_modern:  # To retain backwards compatibility
            print('Please update to the latest versions of the TFRecord maker')
            image_dtype = 'float'
            if 'image' in self.d_type_dict:
                image_dtype = self.d_type_dict['image']
            annotation_dtype = 'int8'
            if 'annotation' in self.d_type_dict:
                annotation_dtype = self.d_type_dict['annotation']
            if 'z_images' in image_features:
                if 'image' in image_features:
                    image_features['image'] = tf.reshape(tf.io.decode_raw(image_features['image'], out_type=image_dtype),
                                                         (image_features['z_images'], image_features['rows'],
                                                          image_features['cols']))
                if 'annotation' in image_features:
                    if 'num_classes' in image_features:
                        image_features['annotation'] = tf.reshape(tf.io.decode_raw(image_features['annotation'],
                                                                                   out_type=annotation_dtype),
                                                                  (image_features['z_images'], image_features['rows'],
                                                                   image_features['cols'], image_features['num_classes']))
                    else:
                        image_features['annotation'] = tf.reshape(tf.io.decode_raw(image_features['annotation'],
                                                                                   out_type=annotation_dtype),
                                                                  (image_features['z_images'], image_features['rows'],
                                                                   image_features['cols']))
            else:
                image_features['image'] = tf.reshape(tf.io.decode_raw(image_features['image'], out_type=image_dtype),
                                                     (image_features['rows'], image_features['cols']))
                if 'num_classes' in image_features:
                    image_features['annotation'] = tf.reshape(tf.io.decode_raw(image_features['annotation'],
                                                                               out_type=annotation_dtype),
                                                              (image_features['rows'], image_features['cols'],
                                                               image_features['num_classes']))
                else:
                    image_features['annotation'] = tf.reshape(tf.io.decode_raw(image_features['annotation'],
                                                                               out_type=annotation_dtype),
                                                              (image_features['rows'], image_features['cols']))
            if 'spacing' in image_features:
                spacing = tf.io.decode_raw(image_features['spacing'], out_type='float32')
                image_features['spacing'] = spacing
            if 'dose' in image_features:
                dose_dtype = 'float'
                if 'dose' in self.d_type_dict:
                    dose_dtype = self.d_type_dict['dose']
                image_features['dose'] = tf.reshape(tf.io.decode_raw(image_features['dose'], out_type=dose_dtype),
                                                    (image_features['dose_images'], image_features['dose_rows'],
                                                     image_features['dose_cols']))
        return image_features


class Decode_Images_Annotations(DecodeImagesAnnotations):
    def __init__(self, **kwargs):
        print('Please move from using Decode_Images_Annotations to DecodeImagesAnnotations, same arguments are passed')
        super().__init__(**kwargs)


class Combine_Liver_Lobe_Segments(ImageProcessor):
    '''
    Combines segments 5, 6, 7 and 8 into 5
    '''

    def parse(self, image_features, *args, **kwargs):
        annotation = image_features['annotation']
        output = [tf.expand_dims(annotation[..., i], axis=-1) for i in range(5)]
        output.append(tf.expand_dims(tf.reduce_sum(annotation[..., 5:], axis=-1), axis=-1))
        output = tf.concat(output, axis=-1)
        image_features['annotation'] = output
        return image_features


class Return_Add_Mult_Disease(ImageProcessor):
    def __init__(self, on_disease=True, change_background=False, cast_to_min=False):
        self.on_disease = on_disease
        self.cast_to_min = cast_to_min
        self.change_background = change_background

    def parse(self, image_features, *args, **kwargs):
        annotation = image_features['annotation']
        if annotation.shape[-1] != 1:
            mask = tf.expand_dims(tf.where(tf.cast(tf.reduce_sum(annotation[..., 1:], axis=-1), 'float16') > .99, 1, 0),
                                  axis=-1)
            if self.on_disease:
                annotation = tf.expand_dims(annotation[..., 2], axis=-1)  # Kick out everything except for the disease
                image_features['annotation'] = annotation
        else:
            mask = tf.where(annotation > 0, 1, 0)
            if self.on_disease:
                annotation = tf.where(annotation == 2, 1, 0)
                image_features['annotation'] = annotation
        image_features['mask'] = mask
        if self.change_background:
            value = 0
            if self.cast_to_min:
                value = tf.reduce_min(image_features['image'])
            image_features['image'] = tf.where(mask == 0, tf.cast(value, dtype=image_features['image'].dtype),
                                               image_features['image'])
        return image_features


class Combine_image_RT_Dose(ImageProcessor):
    def parse(self, input_features, *args, **kwargs):
        image = input_features['image']
        rt = input_features['annotation']
        dose = input_features['dose']
        output = tf.concat([image, rt, dose], axis=-1)
        input_features['combined'] = output
        return input_features


class Fuzzy_Segment_Liver_Lobes(ImageProcessor):
    def __init__(self, min_val=0, max_val=None, num_classes=9):
        '''
        :param variation: margin to expand region, mm. np.arange(start=0, stop=1, step=1), in mm
        '''
        self.min_val = min_val
        self.max_val = max_val
        self.num_classes = num_classes

    def parse(self, image_features, *args, **kwargs):
        if type(image_features) is dict:
            annotation = image_features['annotation']
        else:
            annotation = image_features[-1][-1]
        annotation = tf.cast(annotation, dtype=tf.dtypes.float32)
        filter_size = tf.random.uniform([2], minval=self.min_val, maxval=self.max_val)
        filter_shape = tuple(tf.cast(tf.divide(filter_size, image_features['spacing'][:2]), dtype=tf.dtypes.float32))

        # Explicitly pad the image

        filter_height, filter_width = filter_shape
        pad_top = (filter_height - 1) // 2
        pad_bottom = filter_height - 1 - pad_top
        pad_left = (filter_width - 1) // 2
        pad_right = filter_width - 1 - pad_left
        paddings = [[0, 0], [pad_top, pad_bottom], [pad_left, pad_right], [0, 0]]
        annotation = tf.pad(annotation, paddings, mode='CONSTANT')

        # Filter of shape (filter_width, filter_height, in_channels, 1)
        # has the value of 1 for each element.
        area = tf.math.reduce_prod(filter_shape)
        filter_shape += (tf.shape(annotation)[-1], 1)
        kernel = tf.ones(shape=filter_shape, dtype='float32')

        annotation = tf.nn.depthwise_conv2d(annotation, kernel, strides=(1, 1, 1, 1), padding="VALID")
        annotation = tf.divide(annotation, area)
        annotation = tf.divide(annotation, tf.expand_dims(tf.reduce_sum(annotation, axis=-1), axis=-1))
        image_features['annotation'] = annotation
        return image_features


if __name__ == '__main__':
    pass
