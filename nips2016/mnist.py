import sys, os
sys.path.insert(0, '..')
from lib import models, graph, coarsening, utils

import tensorflow as tf
import numpy as np
import time
from tensorflow.examples.tutorials.mnist import input_data

def grid_graph(m, FLAGS, corners=False):
    z = graph.grid(m)
    dist, idx = graph.distance_sklearn_metrics(z, k=FLAGS.number_edges, metric=FLAGS.metric)
    A = graph.adjacency(dist, idx)

    # Connections are only vertical or horizontal on the grid.
    # Corner vertices are connected to 2 neightbors only.
    if corners:
        import scipy.sparse
        A = A.toarray()
        A[A < A.max()/1.5] = 0
        A = scipy.sparse.csr_matrix(A)
        print('{} edges'.format(A.nnz))

    print("{} > {} edges".format(A.nnz//2, FLAGS.number_edges*m**2//2))
    return A

def main():
    flags = tf.app.flags
    FLAGS = flags.FLAGS

    # Graphs.
    flags.DEFINE_integer('number_edges', 8, 'Graph: minimum number of edges per vertex.')
    flags.DEFINE_string('metric', 'euclidean', 'Graph: similarity measure (between features).')
    # TODO: change cgcnn for combinatorial Laplacians.
    flags.DEFINE_bool('normalized_laplacian', True, 'Graph Laplacian: normalized.')
    flags.DEFINE_integer('coarsening_levels', 4, 'Number of coarsened graphs.')

    # Directories.
    flags.DEFINE_string('dir_data', os.path.join('..', 'data', 'mnist'), 'Directory to store data.')

    t_start = time.process_time()
    A = grid_graph(28, FLAGS, corners=False)
    A = graph.replace_random_edges(A, 0)
    graphs, perm = coarsening.coarsen(A, levels=FLAGS.coarsening_levels, self_connections=False)
    L = [graph.laplacian(A, normalized=True) for A in graphs]
    print('Execution time: {:.2f}s'.format(time.process_time() - t_start))
    #graph.plot_spectrum(L)
    del A
    
    print('Data')
    mnist = input_data.read_data_sets(FLAGS.dir_data, one_hot=False)

    train_data = mnist.train.images.astype(np.float32)
    val_data = mnist.validation.images.astype(np.float32)
    test_data = mnist.test.images.astype(np.float32)
    train_labels = mnist.train.labels
    val_labels = mnist.validation.labels
    test_labels = mnist.test.labels

    t_start = time.process_time()
    train_data = coarsening.perm_data(train_data, perm)
    val_data = coarsening.perm_data(val_data, perm)
    test_data = coarsening.perm_data(test_data, perm)
    print('Execution time: {:.2f}s'.format(time.process_time() - t_start))
    del perm
    
    common = {}
    common['dir_name']       = 'mnist/'
    common['num_epochs']     = 20
    common['batch_size']     = 100
    common['decay_steps']    = mnist.train.num_examples / common['batch_size']
    common['eval_frequency'] = 30 * common['num_epochs']
    common['brelu']          = 'b1relu'
    common['pool']           = 'mpool1'
    C = max(mnist.train.labels) + 1  # number of classes

    model_perf = utils.model_perf()
    name = 'softmax'
    params = common.copy()
    params['dir_name'] += name
    params['regularization'] = 5e-4
    params['dropout']        = 1
    params['learning_rate']  = 0.02
    params['decay_rate']     = 0.95
    params['momentum']       = 0.9
    params['F']              = []
    params['K']              = []
    params['p']              = []
    params['M']              = [C]
    model_perf.test(models.cgcnn(L, **params), name, params,
                    train_data, train_labels, val_data, val_labels, test_data, test_labels)
    
    # Common hyper-parameters for networks with one convolutional layer.
    common['regularization'] = 0
    common['dropout']        = 1
    common['learning_rate']  = 0.02
    common['decay_rate']     = 0.95
    common['momentum']       = 0.9
    common['F']              = [10]
    common['K']              = [20]
    common['p']              = [1]
    common['M']              = [C]
    
    name = 'fgconv_softmax'
    print(name)
    params = common.copy()
    params['dir_name'] += name
    params['filter'] = 'fourier'
    params['K'] = [L[0].shape[0]]
    model_perf.test(models.cgcnn(L, **params), name, params,
                    train_data, train_labels, val_data, val_labels, test_data, test_labels)
    
    name = 'sgconv_softmax'
    print(name)
    params = common.copy()
    params['dir_name'] += name
    params['filter'] = 'spline'
    model_perf.test(models.cgcnn(L, **params), name, params,
                    train_data, train_labels, val_data, val_labels, test_data, test_labels)
    
    name = 'cgconv_softmax'
    print(name)
    params = common.copy()
    params['dir_name'] += name
    params['filter'] = 'chebyshev5'
#    params['filter'] = 'chebyshev2'
#    params['brelu'] = 'b2relu'
    model_perf.test(models.cgcnn(L, **params), name, params,
                    train_data, train_labels, val_data, val_labels, test_data, test_labels)
    
    common['regularization'] = 5e-4
    common['dropout']        = 0.5
    common['learning_rate']  = 0.02  # 0.03 in the paper but sgconv_sgconv_fc_softmax has difficulty to converge
    common['decay_rate']     = 0.95
    common['momentum']       = 0.9
    common['F']              = [32, 64]
    common['K']              = [25, 25]
    common['p']              = [4, 4]
    common['M']              = [512, C]
    
    name = 'fgconv_fgconv_fc_softmax' #  'Non-Param'
    print(name)
    params = common.copy()
    params['dir_name'] += name
    params['filter'] = 'fourier'
    params['K'] = [L[0].shape[0], L[2].shape[0]]
    model_perf.test(models.cgcnn(L, **params), name, params,
                    train_data, train_labels, val_data, val_labels, test_data, test_labels)
    model_perf.show_text()    
                
    name = 'sgconv_sgconv_fc_softmax'  # 'Spline'
    print(name)
    params = common.copy()
    params['dir_name'] += name
    params['filter'] = 'spline'
    model_perf.test(models.cgcnn(L, **params), name, params,
                    train_data, train_labels, val_data, val_labels, test_data, test_labels)
    model_perf.show_text()    

    name = 'cgconv_cgconv_fc_softmax'  # 'Chebyshev'
    print(name)
    params = common.copy()
    params['dir_name'] += name
    params['filter'] = 'chebyshev5'
    model_perf.test(models.cgcnn(L, **params), name, params,
                    train_data, train_labels, val_data, val_labels, test_data, test_labels)
    model_perf.show_text()   
 
if __name__ == "__main__":
    main()
