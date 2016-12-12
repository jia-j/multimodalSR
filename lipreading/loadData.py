"""
.. todo::

    WRITEME
"""
import os
import logging

import numpy
from theano.compat.six.moves import xrange

from pylearn2.datasets import cache, dense_design_matrix
from pylearn2.expr.preprocessing import global_contrast_normalize
from pylearn2.utils import contains_nan
from pylearn2.utils import serial
from pylearn2.utils import string_utils

_logger = logging.getLogger(__name__)


class TCDTIMIT(dense_design_matrix.DenseDesignMatrix):

    """
    .. todo::

        WRITEME

    Parameters
    ----------
    which_set : str
        One of 'train', 'test'
    gcn : float, optional
        Multiplicative constant to use for global contrast normalization.
        No global contrast normalization is applied, if None
    """

    def __init__(self, which_set, center=False, rescale=False, gcn=None,
                 start=None, stop=None, axes=('b', 0, 1, 'c'),
                 toronto_prepro = False, preprocessor = None):
        # note: there is no such thing as the cifar10 validation set; user configurable

        self.axes = axes

        # we define here:
        dtype = 'uint8'
        ntotal = 14600 # for lipspeaker 1: 14627 -> 11.5k train, 1.5k valid, 1.627k test
        ntrain = 13000
        nvalid = 0  # artefact, we won't use it
        ntest = ntotal - ntrain

        # we also expose the following details:
        self.img_shape = (1, 120, 120)
        self.img_size = numpy.prod(self.img_shape)
        self.n_classes = 39
        self.label_names = vocab = [line.rstrip('\n') for line in open('../ImageSpeech/phonemeList.txt')]
        
        # prepare loading
        fnames = ['Lipspkr%i' % i for i in range(1, 1)] #only use lipspeaker 1 for now
        datasets = {}
        datapath = os.path.join('/home/matthijs/TCDTIMIT/database_binary')
        for name in fnames:
            fname = os.path.join(datapath, name)
            if not os.path.exists(fname):
                raise IOError(fname + " was not found. You need to run some scripts")
            datasets[name] = cache.datasetCache.cache_file(fname)
            
# total size of CIFAR10 = 60000 images -> 6 batches of 10000 images
# Loaded in this way, each of the batch files contains a dictionary with the following elements:
#     data -- a 10000x3072 numpy array of uint8s. Each row of the array stores a 32x32 colour image. The first 1024 entries contain the red channel values, the next 1024 the green, and the final 1024 the blue. The image is stored in row-major order, so that the first 32 entries of the array are the red channel values of the first row of the image.
#     labels -- a list of 10000 numbers in the range 0-9. The number at index i indicates the label of the ith image in the array data.
       
       # our batch is 14627 images long -> 14600 to make it round (batch_size in lipreading....py of 50)
        batchLength = ntotal
       
        lenx = int(numpy.ceil((ntrain + nvalid) / float(batchLength)) * batchLength) # 10000 is the batch size
        x = numpy.zeros((lenx, self.img_size), dtype=dtype)
        y = numpy.zeros((lenx, 1), dtype=dtype)

        # load train data
        nloaded = 0
        for i, fname in enumerate(fnames):
            _logger.info('loading file %s' % datasets[fname])
            data = serial.load(datasets[fname]) #dictionary of 'data' and 'labels'
            x[i * batchLength:(i + 1) * batchLength, :] = data['data']
            y[i * batchLength:(i + 1) * batchLength, 0] = data['labels']
            nloaded += batchLength
            if nloaded >= ntrain + nvalid + ntest:
                break

        # # load test data
        # _logger.info('loading file %s' % datasets['test_batch'])
        # data = serial.load(datasets['test_batch'])

        # process this data
        Xs = {'train': x[0:ntrain],
              'test':  x[ntrain:ntotal]}

        Ys = {'train': y[0:ntrain],
              'test':  y[ntrain:ntotal]}

        X = numpy.cast['float32'](Xs[which_set])
        y = Ys[which_set]

        if isinstance(y, list):
            y = numpy.asarray(y).astype(dtype)

        if which_set == 'test':
            assert y.shape[0] == ntest
            y = y.reshape((y.shape[0], 1))

        if center:
            X -= 127.5
        self.center = center

        if rescale:
            X /= 127.5
        self.rescale = rescale

        if toronto_prepro:
            assert not center
            assert not gcn
            X = X / 255.
            if which_set == 'test':
                other = CIFAR10(which_set='train')
                oX = other.X
                oX /= 255.
                X = X - oX.mean(axis=0)
            else:
                X = X - X.mean(axis=0)
        self.toronto_prepro = toronto_prepro

        self.gcn = gcn
        if gcn is not None:
            gcn = float(gcn)
            X = global_contrast_normalize(X, scale=gcn)

        if start is not None:
            # This needs to come after the prepro so that it doesn't
            # change the pixel means computed above for toronto_prepro
            assert start >= 0
            assert stop > start
            assert stop <= X.shape[0]
            X = X[start:stop, :]
            y = y[start:stop, :]
            assert X.shape[0] == y.shape[0]

        if which_set == 'test':
            assert X.shape[0] == ntest

        view_converter = dense_design_matrix.DefaultViewConverter((120, 120, 1),
                                                                  axes)

        super(TCDTIMIT, self).__init__(X=X, y=y, view_converter=view_converter,
                                      y_labels=self.n_classes)

        assert not contains_nan(self.X)

        if preprocessor:
            preprocessor.apply(self)

    def adjust_for_viewer(self, X):
        """
        .. todo::

            WRITEME
        """
        # assumes no preprocessing. need to make preprocessors mark the
        # new ranges
        rval = X.copy()

        # patch old pkl files
        if not hasattr(self, 'center'):
            self.center = False
        if not hasattr(self, 'rescale'):
            self.rescale = False
        if not hasattr(self, 'gcn'):
            self.gcn = False

        if self.gcn is not None:
            rval = X.copy()
            for i in xrange(rval.shape[0]):
                rval[i, :] /= numpy.abs(rval[i, :]).max()
            return rval

        if not self.center:
            rval -= 127.5

        if not self.rescale:
            rval /= 127.5

        rval = numpy.clip(rval, -1., 1.)

        return rval

    def __setstate__(self, state):
        super(CIFAR10, self).__setstate__(state)
        # Patch old pkls
        if self.y is not None and self.y.ndim == 1:
            self.y = self.y.reshape((self.y.shape[0], 1))
        if 'y_labels' not in state:
            self.y_labels = 10

    def adjust_to_be_viewed_with(self, X, orig, per_example=False):
        """
        .. todo::

            WRITEME
        """
        # if the scale is set based on the data, display X oring the
        # scale determined by orig
        # assumes no preprocessing. need to make preprocessors mark
        # the new ranges
        rval = X.copy()

        # patch old pkl files
        if not hasattr(self, 'center'):
            self.center = False
        if not hasattr(self, 'rescale'):
            self.rescale = False
        if not hasattr(self, 'gcn'):
            self.gcn = False

        if self.gcn is not None:
            rval = X.copy()
            if per_example:
                for i in xrange(rval.shape[0]):
                    rval[i, :] /= numpy.abs(orig[i, :]).max()
            else:
                rval /= numpy.abs(orig).max()
            rval = numpy.clip(rval, -1., 1.)
            return rval

        if not self.center:
            rval -= 127.5

        if not self.rescale:
            rval /= 127.5

        rval = numpy.clip(rval, -1., 1.)

        return rval

    def get_test_set(self):
        """
        .. todo::

            WRITEME
        """
        return CIFAR10(which_set='test', center=self.center,
                       rescale=self.rescale, gcn=self.gcn,
                       toronto_prepro=self.toronto_prepro,
                       axes=self.axes)
