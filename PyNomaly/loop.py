from math import erf
import numpy as np
import sys
import warnings


__author__ = 'Valentino Constantinou'
__version__ = '0.1.5'
__license__ = 'Apache License, Version 2.0'


class LocalOutlierProbability(object):
    """
    :param data: a Pandas DataFrame or Numpy array of float data
    :param extent: a parameter value in the range (0, 1] that controls the statistical extent (optional, default 0.997)
    :param n_neighbors: the total number of neighbors to consider w.r.t. each sample (optional, default 10)
    :param cluster_labels: a numpy array of cluster assignments w.r.t. each sample (optional, default None)
    :return:
    """"""

    Based on the work of Kriegel, Kröger, Schubert, and Zimek (2009) in LoOP: Local Outlier Probabilities.
    ----------

    References
    ----------
    .. [1] Breunig M., Kriegel H.-P., Ng R., Sander, J. LOF: Identifying Density-based Local Outliers. ACM SIGMOD
           International Conference on Management of Data (2000).
    .. [2] Kriegel H., Kröger P., Schubert E., Zimek A. LoOP: Local Outlier Probabilities. 18th ACM conference on
    """

    def accepts(*types):
        def decorator(f):
            assert len(types) == f.__code__.co_argcount

            def new_f(*args, **kwds):
                for (a, t) in zip(args, types):
                    if type(a).__name__ == 'DataFrame':
                        a = np.array(a)
                    if isinstance(a, t) is False:
                        warnings.warn("Argument %r is not of type %s" % (a, t), UserWarning)
                        sys.exit()
                opt_types = {
                    'extent': {
                        'type': types[2]
                    },
                    'n_neighbors': {
                        'type': types[3]
                    },
                    'cluster_labels': {
                        'type': types[4]
                    }
                }
                for x in kwds:
                    opt_types[x]['value'] = kwds[x]
                for k in opt_types:
                    try:
                        if isinstance(opt_types[k]['value'], opt_types[k]['type']) is False:
                            warnings.warn("Argument %r is not of type %s" % (k, opt_types[k]['type']), UserWarning)
                            sys.exit()
                    except KeyError:
                        pass
                return f(*args, **kwds)
            new_f.__name__ = f.__name__
            return new_f
        return decorator

    @accepts(object, np.ndarray, float, int, (list, np.ndarray))
    def __init__(self, data, extent=0.997, n_neighbors=10, cluster_labels=None):
        self.data = data
        self.extent = extent
        self.n_neighbors = n_neighbors
        self.cluster_labels = cluster_labels
        self.local_outlier_probabilities = None
        if not self.n_neighbors > 0:
            warnings.warn('n_neighbors must be greater than 0. Execution halted.', UserWarning)
            sys.exit()
        if not 0. < self.extent <= 1.:
            warnings.warn('Statistical extent must be in (0,1]. Execution halted.', UserWarning)
            sys.exit()
        if np.any(np.isnan(self.data)):
            warnings.warn('Input data contains missing values. Some scores may not be returned.', UserWarning)

    @staticmethod
    def _standard_distance(mean_distance, sum_squared_distance):
        with np.errstate(divide='ignore', invalid='ignore'):
            st_dist = np.sqrt(np.divide(sum_squared_distance, np.fabs(mean_distance)))
        return st_dist

    @staticmethod
    def _prob_set_distance(extent, standard_distance):
        return 1.0 / (extent * standard_distance)

    @staticmethod
    def _prob_outlier_factor(probabilistic_set_distance, ev_prob_dist):
        return (probabilistic_set_distance / ev_prob_dist) - 1

    @staticmethod
    def _norm_prob_outlier_factor(extent, ev_probabilistic_outlier_factor):
        return extent * np.sqrt(ev_probabilistic_outlier_factor)

    @staticmethod
    def _local_outlier_probability(plof_val, nplof_val):
        erf_vec = np.vectorize(erf)
        return np.maximum(0, erf_vec(plof_val / (nplof_val * np.sqrt(2.0))))

    def _n_observations(self):
        return len(self.data)

    def _store(self):
        return np.empty([self._n_observations(), 3])

    def _cluster_labels(self):
        if self.cluster_labels is None:
            return np.array([0] * len(self.data))
        else:
            return self.cluster_labels

    def _distances(self, data_store):
        for cluster_id in set(self._cluster_labels()):
            indices = np.where(self._cluster_labels() == cluster_id)
            if self.data.__class__.__name__ == 'DataFrame':
                points_vector = self.data.iloc[indices].values
            elif self.data.__class__.__name__ == 'ndarray':
                points_vector = self.data.take(indices, axis=0)
                points_vector = points_vector.reshape(points_vector.shape[1:])
            d = np.tril((points_vector[:, np.newaxis] - points_vector), -1)
            for vec in range(d.shape[1]):
                neighborhood_distances = np.sort(np.mean(np.sqrt(d[:, vec] ** 2), axis=1))[1:self.n_neighbors + 1]
                neighborhood_dist = np.mean(neighborhood_distances)
                closest_neighbor_distance = neighborhood_distances[1:2]
                data_store[indices[0][vec]] = np.array([cluster_id, neighborhood_dist, closest_neighbor_distance])
            if not data_store[:, 1].any():
                warnings.warn('Neighborhood distances all zero. Use a larger value for n_neighbors.', RuntimeWarning)
                sys.exit()
        return data_store

    def _ssd(self, data_store):
        self.cluster_labels_u = np.unique(data_store[:, 0])
        ssd_dict = {}
        for cluster_id in self.cluster_labels_u:
            indices = np.where(data_store[:, 0] == cluster_id)
            cluster_distances = np.take(data_store[:, 1], indices)
            cluster_distances_nonan = cluster_distances[np.logical_not(np.isnan(cluster_distances))]
            ssd = np.sum(np.power(cluster_distances_nonan, 2))
            if ssd == 0.0:
                warnings.warn('Sum of square distances equals zero. Execution halted.', RuntimeWarning)
                sys.exit()
            ssd_dict[cluster_id] = ssd
        data_store = np.hstack((data_store, np.array([[ssd_dict[x] for x in data_store[:, 0].tolist()]]).T))
        return data_store

    def _standard_distances(self, data_store):
        return np.hstack(
            (data_store,
             np.array([np.apply_along_axis(self._standard_distance, 0, data_store[:, 1], data_store[:, 3])]).T))

    def _prob_set_distances(self, data_store):
        return np.hstack((data_store, np.array([self._prob_set_distance(self.extent, data_store[:, 4])]).T))

    def _prob_set_distances_ev(self, data_store):
        prob_set_distance_ev_dict = {}
        for cluster_id in self.cluster_labels_u:
            indices = np.where(data_store[:, 0] == cluster_id)
            prob_set_distances = np.take(data_store[:, 5], indices)
            prob_set_distances_nonan = prob_set_distances[np.logical_not(np.isnan(prob_set_distances))]
            prob_set_distance_ev_dict[cluster_id] = np.mean(prob_set_distances_nonan)
        data_store = np.hstack(
            (data_store, np.array([[prob_set_distance_ev_dict[x] for x in data_store[:, 0].tolist()]]).T))
        return data_store

    def _prob_local_outlier_factors(self, data_store):
        return np.hstack(
            (data_store,
             np.array([np.apply_along_axis(self._prob_outlier_factor, 0, data_store[:, 5], data_store[:, 6])]).T))

    def _prob_local_outlier_factors_ev(self, data_store):
        prob_local_outlier_factor_ev_dict = {}
        for cluster_id in self.cluster_labels_u:
            indices = np.where(data_store[:, 0] == cluster_id)
            prob_local_outlier_factors = np.take(data_store[:, 7], indices)
            prob_local_outlier_factors_nonan = prob_local_outlier_factors[
                np.logical_not(np.isnan(prob_local_outlier_factors))]
            prob_local_outlier_factor_ev_dict[cluster_id] = np.sum(np.power(prob_local_outlier_factors_nonan, 2)) / \
                float(prob_local_outlier_factors_nonan.size)
        data_store = np.hstack(
            (data_store, np.array([[prob_local_outlier_factor_ev_dict[x] for x in data_store[:, 0].tolist()]]).T))
        return data_store

    def _norm_prob_local_outlier_factors(self, data_store):
        return np.hstack((data_store, np.array([self._norm_prob_outlier_factor(self.extent, data_store[:, 8])]).T))

    def _local_outlier_probabilities(self, data_store):
        return np.hstack(
            (data_store,
             np.array([np.apply_along_axis(self._local_outlier_probability, 0, data_store[:, 7], data_store[:, 9])]).T))

    def fit(self):
        store = self._store()
        store = self._distances(store)
        store = self._ssd(store)
        store = self._standard_distances(store)
        store = self._prob_set_distances(store)
        store = self._prob_set_distances_ev(store)
        store = self._prob_local_outlier_factors(store)
        store = self._prob_local_outlier_factors_ev(store)
        store = self._norm_prob_local_outlier_factors(store)
        store = self._local_outlier_probabilities(store)

        self.local_outlier_probabilities = store[:, 10]

        return self.local_outlier_probabilities
