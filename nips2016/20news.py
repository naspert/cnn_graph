import sys, os
sys.path.insert(0, '..')
from lib import models, graph, coarsening, utils

import tensorflow as tf
import matplotlib.pyplot as plt
import scipy.sparse
import numpy as np
import time


def main():
    flags = tf.app.flags
    FLAGS = flags.FLAGS

    # Graphs.
    flags.DEFINE_integer('number_edges', 16, 'Graph: minimum number of edges per vertex.')
    flags.DEFINE_string('metric', 'cosine', 'Graph: similarity measure (between features).')
    # TODO: change cgcnn for combinatorial Laplacians.
    flags.DEFINE_bool('normalized_laplacian', True, 'Graph Laplacian: normalized.')
    flags.DEFINE_integer('coarsening_levels', 0, 'Number of coarsened graphs.')

    flags.DEFINE_string('dir_data', os.path.join('..', 'data', '20news'), 'Directory to store data.')
    flags.DEFINE_integer('val_size', 400, 'Size of the validation set.')
    
    # Fetch dataset. Scikit-learn already performs some cleaning.
    remove = ('headers','footers','quotes')  # (), ('headers') or ('headers','footers','quotes')
    train = utils.Text20News(data_home=FLAGS.dir_data, subset='train', remove=remove)

    # Pre-processing: transform everything to a-z and whitespace.
    #print(train.show_document(1)[:400])
    train.clean_text(num='substitute')

    # Analyzing / tokenizing: transform documents to bags-of-words.
    #stop_words = set(sklearn.feature_extraction.text.ENGLISH_STOP_WORDS)
    # Or stop words from NLTK.
    # Add e.g. don, ve.
    train.vectorize(stop_words='english')
    #print(train.show_document(1)[:400])
    
    # Word embedding
    
    train.embed()
    train.data_info()
    
    # Feature selection.
    # Other options include: mutual information or document count.
    freq = train.keep_top_words(1000, 20)
    train.data_info()
    train.show_document(1)
    #plt.figure(figsize=(17,5))
    #plt.semilogy(freq);

    # Remove documents whose signal would be the zero vector.
    wc = train.remove_short_documents(nwords=5, vocab='selected')
    train.data_info(True)
    
    train.normalize(norm='l1')
    train.show_document(1)
    
    # Test dataset.
    test = utils.Text20News(data_home=FLAGS.dir_data, subset='test', remove=remove)
    test.clean_text(num='substitute')
    test.vectorize(vocabulary=train.vocab)
    test.data_info()
    wc = test.remove_short_documents(nwords=5, vocab='selected')
    print('shortest: {}, longest: {} words'.format(wc.min(), wc.max()))
    test.data_info(True)
    test.normalize(norm='l1')
    
    
    train_data = train.data.astype(np.float32)
    test_data = test.data.astype(np.float32)
    train_labels = train.labels
    test_labels = test.labels
    
    graph_data = train.embeddings.astype(np.float32)
    
    t_start = time.process_time()
    dist, idx = graph.distance_sklearn_metrics(graph_data, k=FLAGS.number_edges, metric=FLAGS.metric)
    A = graph.adjacency(dist, idx)
    print("{} > {} edges".format(A.nnz//2, FLAGS.number_edges*graph_data.shape[0]//2))
    A = graph.replace_random_edges(A, 0)
    graphs, perm = coarsening.coarsen(A, levels=FLAGS.coarsening_levels, self_connections=False)
    L = [graph.laplacian(A, normalized=True) for A in graphs]
    print('Execution time: {:.2f}s'.format(time.process_time() - t_start))
    
    t_start = time.process_time()
    train_data = scipy.sparse.csr_matrix(coarsening.perm_data(train_data.toarray(), perm))
    test_data = scipy.sparse.csr_matrix(coarsening.perm_data(test_data.toarray(), perm))
    print('Execution time: {:.2f}s'.format(time.process_time() - t_start))
    del perm
    
    # Training set is shuffled already.
    #perm = np.random.permutation(train_data.shape[0])
    #train_data = train_data[perm,:]
    #train_labels = train_labels[perm]

    # Validation set.
    
    val_data = test_data
    val_labels = test_labels
    
    utils.baseline(train_data, train_labels, test_data, test_labels)
    common = {}
    common['dir_name']       = '20news/'
    common['num_epochs']     = 80
    common['batch_size']     = 100
    common['decay_steps']    = len(train_labels) / common['batch_size']
    common['eval_frequency'] = 5 * common['num_epochs']
    common['filter']         = 'chebyshev5'
    common['brelu']          = 'b1relu'
    common['pool']           = 'mpool1'
    common['use_gradient']   = False
    C = max(train_labels) + 1  # number of classes

    model_perf = utils.model_perf()
    name = 'softmax'
    print(name)
    params = common.copy()
    params['dir_name'] += name
    params['regularization'] = 0
    params['dropout']        = 1
    params['learning_rate']  = 1e3
    params['decay_rate']     = 0.95
    params['momentum']       = 0.9
    params['F']              = []
    params['K']              = []
    params['p']              = []
    params['M']              = [C]
    model_perf.test(models.cgcnn(L, **params), name, params,
                    train_data, train_labels, val_data, val_labels, test_data, test_labels)
                    
    name = 'fc_softmax'
    print(name)
    params = common.copy()
    params['dir_name'] += name
    params['regularization'] = 0
    params['dropout']        = 1
    params['learning_rate']  = 0.1
    params['decay_rate']     = 0.95
    params['momentum']       = 0.9
    params['F']              = []
    params['K']              = []
    params['p']              = []
    params['M']              = [2500, C]
    model_perf.test(models.cgcnn(L, **params), name, params,
                    train_data, train_labels, val_data, val_labels, test_data, test_labels)
    
    name = 'fc_fc_softmax'
    print(name)
    params = common.copy()
    params['dir_name'] += name
    params['regularization'] = 0
    params['dropout']        = 1
    params['learning_rate']  = 0.1
    params['decay_rate']     = 0.95
    params['momentum']       = 0.9
    params['F']              = []
    params['K']              = []
    params['p']              = []
    params['M']              = [2500, 500, C]
    model_perf.test(models.cgcnn(L, **params), name, params,
                    train_data, train_labels, val_data, val_labels, test_data, test_labels)
                    
    name = 'fgconv_softmax'
    print(name)
    params = common.copy()
    params['dir_name'] += name
    params['filter']         = 'fourier'
    params['regularization'] = 0
    params['dropout']        = 1
    params['learning_rate']  = 0.001
    params['decay_rate']     = 1
    params['momentum']       = 0
    params['F']              = [32]
    params['K']              = [L[0].shape[0]]
    params['p']              = [1]
    params['M']              = [C]
    model_perf.test(models.cgcnn(L, **params), name, params,
                    train_data, train_labels, val_data, val_labels, test_data, test_labels)
                    
    name = 'sgconv_softmax'
    print(name)
    params = common.copy()
    params['dir_name'] += name
    params['filter']         = 'spline'
    params['regularization'] = 1e-3
    params['dropout']        = 1
    params['learning_rate']  = 0.1
    params['decay_rate']     = 0.999
    params['momentum']       = 0
    params['F']              = [32]
    params['K']              = [5]
    params['p']              = [1]
    params['M']              = [C]
    model_perf.test(models.cgcnn(L, **params), name, params,
                    train_data, train_labels, val_data, val_labels, test_data, test_labels)
                    
    name = 'cgconv_softmax'
    print(name)
    params = common.copy()
    params['dir_name'] += name
    params['regularization'] = 1e-3
    params['dropout']        = 1
    params['learning_rate']  = 0.1
    params['decay_rate']     = 0.999
    params['momentum']       = 0
    params['F']              = [32]
    params['K']              = [5]
    params['p']              = [1]
    params['M']              = [C]
    model_perf.test(models.cgcnn(L, **params), name, params,
                    train_data, train_labels, val_data, val_labels, test_data, test_labels)
                    
    name = 'cgconv_fc_softmax'
    params = common.copy()
    params['dir_name'] += name
    params['regularization'] = 0
    params['dropout']        = 1
    params['learning_rate']  = 0.1
    params['decay_rate']     = 0.999
    params['momentum']       = 0
    params['F']              = [5]
    params['K']              = [15]
    params['p']              = [1]
    params['M']              = [100, C]
    model_perf.test(models.cgcnn(L, **params), name, params,
                    train_data, train_labels, val_data, val_labels, test_data, test_labels)
                    
    model_perf.show_text()
    
if __name__ == "__main__":
    main()