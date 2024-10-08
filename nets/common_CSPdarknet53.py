from functools import wraps, reduce

from tensorflow.keras import backend as K
#import tensorflow as tf
from tensorflow.keras.initializers import RandomNormal
from tensorflow.keras.layers import (LeakyReLU, Add, Concatenate,BatchNormalization, 
                                     Conv2D, Conv3D, Layer, ZeroPadding2D, ZeroPadding3D)
from tensorflow.keras.regularizers import l2
#from utils.utils import compose

def compose(*funcs):
    '''   
    reduce(fun,seq) is used to apply a particular function passed in its argument to all of the list elements mentioned in the sequence:      
    1, At first step, first two elements of sequence are picked and the result is obtained.
    2, Next step is to apply the same function to the previously attained result and the number just succeeding the second element and the result is again stored.
    3, This process continues till no more elements are left in the container.

    '''
    if funcs: #https://www.geeksforgeeks.org/reduce-in-python/  https://www.geeksforgeeks.org/python-lambda-anonymous-functions-filter-map-reduce/
        return reduce(lambda f, g: lambda *a, **kw: g(f(*a, **kw)), funcs)#Mish(BatchNormalization(DarknetConv2D(*args, **no_bias_kwargs)))
    else:
        raise ValueError('Composition of empty sequence not supported.')
        
class Mish(Layer):
    def __init__(self, **kwargs):
        super(Mish, self).__init__(**kwargs)
        self.supports_masking = True

    def call(self, inputs):
        return inputs * K.tanh(K.softplus(inputs))#x*tanh(log(exp(x) + 1))
        #return inputs * tf.math.tanh(tf.math.softplus(inputs))#x*tanh(log(exp(x) + 1))

    def get_config(self):
        config = super(Mish, self).get_config()
        return config

    def compute_output_shape(self, input_shape):
        return input_shape


@wraps(Conv2D)
def DarknetConv2D(*args, **kwargs):
    """ 2D convolutional layer in this research 
    Args:
        input_tensor        ->          input 2D tensor, [None, w, h, channels]
        filters             ->          output channels, int
        kernel_size         ->          kernel size, int
        strides             ->          strides, tuple, (strides, strides)
        padding             ->          "same" or "valid", no captical letters
        activation          ->          "leaky_relu" or "mish"
    """    
    darknet_conv_kwargs = {'kernel_initializer' : RandomNormal(stddev=0.02), 'kernel_regularizer' : l2(kwargs.get('weight_decay', 5e-4))}
    darknet_conv_kwargs['padding'] = 'valid' if kwargs.get('strides')==(2, 2) else 'same'   
    try:
        del kwargs['weight_decay']
    except:
        pass
    darknet_conv_kwargs.update(kwargs)
    return Conv2D(*args, **darknet_conv_kwargs)


@wraps(Conv3D)
def DarknetConv3D(*args, **kwargs):
    """ 3D convolutional layer in this research 
    Args:
        input_tensor        ->          input 3D tensor, [None, w, h, d, channels]
        filters             ->          output channels, int
        kernel_size         ->          kernel size, int
        strides             ->          strides, tuple, (strides, strides, strides)
        padding             ->          "same" or "valid", no captical letters
        activation          ->          "leaky_relu" or "mish"
        use_bias            ->          False, batch_normalization and use_bias cannot co-exist
        padding             ->          'valid', no padding for 'strides'==(2, 2, 2), otherwise 'same'
        
    Conv3D(filters=filters, kernel_size=kernel_size, strides=strides, padding=padding, 
           activation=None, use_bias=use_bias, kernel_initializer='glorot_uniform', 
           bias_initializer='zeros', kernel_regularizer=None, bias_regularizer=None, 
           )(input_tensor)
    """
    ##### NOTE: batch_normalization and use_bias cannot co-exist #####
    darknet_conv_kwargs = {'kernel_initializer' : RandomNormal(stddev=0.02), 'kernel_regularizer' : l2(kwargs.get('weight_decay', 5e-4))}
    darknet_conv_kwargs['padding'] = 'valid' if kwargs.get('strides')==(2, 2, 2) else 'same'   
    try:
        del kwargs['weight_decay']
    except:
        pass
    darknet_conv_kwargs.update(kwargs)
    return Conv3D(*args, **darknet_conv_kwargs)



def DarknetConv2D_BN_Mish(*args, **kwargs):
    no_bias_kwargs = {'use_bias': False}
    no_bias_kwargs.update(kwargs)
    return compose(
        DarknetConv2D(*args, **no_bias_kwargs),
        BatchNormalization(),
        Mish())


def DarknetConv3D_BN_Mish(*args, **kwargs):
    no_bias_kwargs = {'use_bias': False}
    no_bias_kwargs.update(kwargs)
    return compose(
        DarknetConv3D(*args, **no_bias_kwargs),
        BatchNormalization(),
        Mish())

def resblock(x, Conv, num_filters,kernel1,kernel2, all_narrow, weight_decay=5e-4):
    # y = DarknetConv2D_BN_Mish(num_filters//2, (1,1), weight_decay=weight_decay)(x)
    # y = DarknetConv2D_BN_Mish(num_filters//2 if all_narrow else num_filters, (3,3), weight_decay=weight_decay))(y)
    # x = Add()([x,y])
    y = compose(
            Conv(num_filters//2, kernel1, weight_decay=weight_decay),
            Conv(num_filters//2 if all_narrow else num_filters, kernel2, weight_decay=weight_decay))(x)
    x = Add()([x,y])

    return x

def resblock_body(x, num_filters, num_blocks, all_narrow=True, weight_decay=5e-4,kernel1=(1,1),kernel2=(3,3)):

    preconv1 = ZeroPadding2D(((1,0),(1,0)))(x) 
    preconv1 = DarknetConv2D_BN_Mish(num_filters, kernel2, strides=(2,2), weight_decay=weight_decay)(preconv1)


    shortconv = DarknetConv2D_BN_Mish(num_filters//2 if all_narrow else num_filters, kernel1, weight_decay=weight_decay)(preconv1)


    mainconv = DarknetConv2D_BN_Mish(num_filters//2 if all_narrow else num_filters, kernel1, weight_decay=weight_decay)(preconv1)
 
    for i in range(num_blocks):
        mainconv = resblock(mainconv, DarknetConv2D_BN_Mish, num_filters,kernel1,kernel2, all_narrow, weight_decay)
  
    postconv = DarknetConv2D_BN_Mish(num_filters//2 if all_narrow else num_filters, kernel1, weight_decay=weight_decay)(mainconv)


    route = Concatenate()([postconv, shortconv])


    return DarknetConv2D_BN_Mish(num_filters, kernel1, weight_decay=weight_decay)(route)


def resblock_body_3D(x, num_filters, num_blocks, all_narrow=True, weight_decay=5e-4,kernel1=(1,1,1),kernel2=(3,3,3)):

    preconv1 = ZeroPadding3D(((1,0),(1,0),(1,0)))(x)     #preconv1.shape
    preconv1 = DarknetConv3D_BN_Mish(num_filters, kernel2, strides=(2,2,2), weight_decay=weight_decay)(preconv1)


    shortconv = DarknetConv3D_BN_Mish(num_filters//2 if all_narrow else num_filters, kernel1, weight_decay=weight_decay)(preconv1)


    mainconv = DarknetConv3D_BN_Mish(num_filters//2 if all_narrow else num_filters, kernel1, weight_decay=weight_decay)(preconv1)
  
    for i in range(num_blocks):
        mainconv = resblock(mainconv, DarknetConv3D_BN_Mish, num_filters,kernel1,kernel2, all_narrow, weight_decay)
       
    postconv = DarknetConv3D_BN_Mish(num_filters//2 if all_narrow else num_filters, kernel1, weight_decay=weight_decay)(mainconv)


    route = Concatenate()([postconv, shortconv])


    return DarknetConv3D_BN_Mish(num_filters, kernel1, weight_decay=weight_decay)(route)





def darknet_body_3D(x, weight_decay=5e-4):
    #input_channel = x.shape[-1] # input_channel is filters
    #x = DarknetConv2D_BN_Mish(input_channel, 1, weight_decay=weight_decay)(x)
    x = DarknetConv3D_BN_Mish(16, 1, weight_decay=weight_decay)(x) #x.shape: [None, 256, 256, 64, 32]
    x = resblock_body_3D(x, 16, 2, False, weight_decay=weight_decay)
    x = resblock_body_3D(x, 16, 4, weight_decay=weight_decay)
    x = resblock_body_3D(x, 32, 4, weight_decay=weight_decay)
    feat1 = x
    x = resblock_body_3D(x, 64, 4, weight_decay=weight_decay)
    feat2 = x
    # x = resblock_body_3D(x, 128, 4, weight_decay=weight_decay)
    # feat3 = x
    # return feat1,feat2,feat3
    return feat2
