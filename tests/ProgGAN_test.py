from GANLib import ProgGAN
from GANLib import plotter
from GANLib import utils

from keras.datasets import mnist, fashion_mnist, cifar10
from keras.layers import Input, Dense, Reshape, Flatten, Dropout, concatenate, add, RepeatVector, UpSampling2D
from keras.layers import BatchNormalization, Activation, Embedding, ZeroPadding2D, AveragePooling2D, Lambda
from keras.layers.advanced_activations import LeakyReLU
from keras.layers.convolutional import UpSampling2D, Conv2D
from keras.models import Model
from keras.optimizers import Adam, RMSprop, Nadam

import matplotlib.pyplot as plt
import numpy as np

from keras.utils import plot_model


def new_sheet(self, filters, kernel_size, padding, name, trainable = True):
    def func(layer):
        w = self.weights.get(name,None)
        layer = Conv2D(filters, kernel_size, padding=padding, weights = w, name = name, trainable = trainable)(layer)
        layer = LeakyReLU(alpha=0.2)(layer) 
        return layer
    return func

def build_generator(self):
    previous_step = None
    next_step = None

    input_layer = Input(shape=(self.latent_dim,))
    layer = RepeatVector(16)(input_layer)
    layer = Reshape((4, 4, self.latent_dim))(layer)
    
    layer = new_sheet(self, 64, (4,4), 'same', 'genr_head_0')(layer)
    layer = utils.PixelNorm()(layer)
    #layer = new_sheet(self, 64, (3,3), 'same', 'genr_head_1')(layer)
    #layer = utils.PixelNorm()(layer)
    
    #Growing layers
    for i in range(self.layers):
        layer = UpSampling2D(2)(layer)
        previous_step = layer
        
        layer = new_sheet(self, 64, (3,3), 'same', 'genr_layer_0'+str(i))(layer)
        layer = utils.PixelNorm()(layer)
        #layer = new_sheet(self, 64, (3,3), 'same', 'genr_layer_1'+str(i))(layer)
        #layer = utils.PixelNorm()(layer)
   
    next_step = Conv2D(self.channels, (1,1), name = 'to_rgb')(layer) #to RGB
    
    
    #smooth fading
    if previous_step is not None: 
        previous_step = Conv2D(self.channels, (1,1), weights = self.weights.get('to_rgb',None))(previous_step) 
        
        previous_step = Lambda(lambda x: x * (1 - self.transition_alpha.tensor))(previous_step)
        next_step = Lambda(lambda x: x * self.transition_alpha.tensor)(next_step)
        layer = add([previous_step, next_step])
    else:
        layer = next_step
        
    return Model(input_layer, layer)
    
def build_discriminator(self):
    previous_step = None
    next_step = None
    
    input_layer = Input(shape=self.inp_shape)
    layer = input_layer
    
    layer = Conv2D(64, (1,1), name = 'from_rgb')(layer) #from RGB
    layer = LeakyReLU(alpha=0.2)(layer) 
    
    #Growing layers
    for i in range(self.layers, 0, -1):
        layer = new_sheet(self, 64, (3,3), 'same', 'disc_layer_0'+str(i))(layer)
        #layer = new_sheet(self, 64, (3,3), 'same', 'disc_layer_1'+str(i))(layer)
        layer = AveragePooling2D(2)(layer)
        
        #smooth fading
        if i == self.layers:
            next_step = layer
            
            previous_step = AveragePooling2D(2)(input_layer)
            previous_step = Conv2D(64, (1,1), weights = self.weights.get('from_rgb',None))(previous_step) #from RGB
            previous_step = LeakyReLU(alpha=0.2)(previous_step) 
        
            previous_step = Lambda(lambda x: x * (1 - self.transition_alpha.tensor))(previous_step)
            next_step = Lambda(lambda x: x * self.transition_alpha.tensor)(next_step)
            layer = add([previous_step, next_step]) 
                
    
    layer = utils.MiniBatchStddev(group_size=4)(layer)
    #layer = new_sheet(self, 64, (3,3), 'same', 'disc_head_0')(layer)
    layer = new_sheet(self, 64, (4,4), 'valid', 'disc_head_1')(layer)
    
    layer = Flatten()(layer)
    #layer = Dense(256, weights = self.weights.get('disc_head_1',None), name = 'disc_head_1')(layer)
    #layer = LeakyReLU(alpha=0.2)(layer) 
    
    layer = Dense(1, activation=self.disc_activation)(layer)

    return Model(input_layer, layer)


       
noise_dim = 100    
r, c = 3, 4
noise = np.random.uniform(-1, 1, (r * c, noise_dim))

def sample_images(gen, file):
    gen_imgs = gen.predict([noise])

    # Rescale images 0 - 1
    gen_imgs = 0.5 * gen_imgs + 0.5
    gen_imgs = np.clip(gen_imgs,0,1)
    
    fig, axs = plt.subplots(r, c)
    cnt = 0
    for i in range(r):
        for j in range(c):
            if gen_imgs.shape[-1] == 1: 
                axs[i,j].imshow(gen_imgs[cnt,:,:,0], cmap='gray')
            else:
                axs[i,j].imshow(gen_imgs[cnt,:,:])
            axs[i,j].axis('off')
            cnt += 1
    fig.savefig(file) #% epoch
    plt.close()   
    
    
img_path = 'ProgGAN'
mode = 'vanilla'
    
# Load the dataset
#(X_train, labels), (_, _) = cifar10.load_data()
#indx = np.where(labels == 1)[0]
#X_train = X_train[indx]

X_train = np.load('../../Datasets/Faces/face_images_128x128.npy')

# Configure input
X_train = (X_train.astype(np.float32) - 127.5) / 127.5
if len(X_train.shape)<4:
    X_train = np.expand_dims(X_train, axis=3)
    
    
#Run GAN for 20000 iterations
gan = ProgGAN(X_train.shape[1:], noise_dim, mode = mode)
gan.build_generator = lambda self=gan: build_generator(self)
gan.build_discriminator = lambda self=gan: build_discriminator(self)

#optimizer = Adam(0.001, beta_1=0., beta_2=0.99, epsilon=1e-8)
gan.build_models(optimizer = Adam(0.001, beta_1=0., beta_2=0.99, epsilon=1e-8))


ind = 0
def callback():
    global ind 
    ind+=1
    path = 'images/'+img_path+'/'
    sample_images(gan.generator, path+'imgs/'+str(ind)+'.png')
    #plotter.save_hist_image(gan.history, path+'_hist.png')
    
    #[1000, 2000, 3000, 5000, 8000, 13000]
gan.train(X_train, epochs_list = [1000, 2000, 3000, 5000, 8000, 13000], batch_size_list=[16, 16, 16, 16, 8, 4], checkpoint_callback = callback, validation_split = 0.1)    