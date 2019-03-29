"""Data related functionalities.

This modules contains the tools to preprare the data, from the raw csv files, to the DataFlow
objects will be used to fit our models.

The easiest way is to use the :attr:`load_data` function, that will return a TGANDataset object,
that we can use to fit our model.





"""


import json

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture
from tensorpack import DataFlow, RNGDataFlow


def check_metadata(metadata):
    """Check that the given metadata has correct types for all its members.

    Args:
        metadata(dict): Description of the inputs.

    Returns:
        None

    Raises:
        AssertionError: If any of the details is not valid.

    """
    message = 'The given metadata contains unsupported types.'
    assert all([item['type'] in ['category', 'value'] for item in metadata['details']]), message


def check_inputs(function):
    """Validate inputs for functions whose first argument is a numpy.ndarray with shape (n,1).

    Args:
        function(callable): Method to validate.

    Returns:
        callable: Will check the inputs before calling :attr:`function`.

    Raises:
        ValueError: If first argument is not a valid :class:`numpy.array` of shape (n, 1).

    """
    def decorated(self, data, *args, **kwargs):
        if not (isinstance(data, np.ndarray) and len(data.shape) == 2 and data.shape[1] == 1):
            raise ValueError('The argument `data` must be a numpy.ndarray with shape (n, 1).')

        return function(self, data, *args, **kwargs)

    decorated.__doc__ == function.__doc__
    return decorated


class NpDataFlow(RNGDataFlow):
    """Subclass of :class:`tensorpack.RNGDataFlow` prepared to work with :class:`numpy.ndarray`.

    Attributes:
        shuffle(bool): Wheter or not to shuffle the data.
        info(dict): Metadata for the given :attr:`data`.
        num_features(int): Number of features in given data.
        data(list): Prepared data from :attr:`filename`.
        distribution(list): DepecrationWarning?

    """

    def __init__(self, data, metadata, shuffle=True):
        """Initialize object.

        Args:
            filename(str): Path to the json file containing the metadata.
            shuffle(bool): Wheter or not to shuffle the data.

        Raises:
            ValueError: If any column_info['type'] is not supported

        """
        self.shuffle = shuffle

        self.metadata = metadata
        self.num_features = self.metadata['num_features']

        self.data = []
        self.distribution = []
        for column_id, column_info in enumerate(self.metadata['details']):
            if column_info['type'] == 'value':
                col_data = data['f%02d' % column_id]
                value = col_data[:, :1]
                cluster = col_data[:, 1:]
                self.data.append(value)
                self.data.append(cluster)

            elif column_info['type'] == 'category':
                col_data = np.asarray(data['f%02d' % column_id], dtype='int32')
                self.data.append(col_data)

            else:
                raise ValueError(
                    "column_info['type'] must be either 'category' or 'value'."
                    "Instead it was '{}'.".format(column_info['type'])
                )

        self.data = list(zip(*self.data))

    def size(self):
        """Return the number of rows in data.

        Returns:
            int: Number of rows in :attr:`data`.

        """
        return len(self.data)

    def get_data(self):
        """Yield the rows from :attr:`data`.

        Yields:
            tuple: Row of data.

        """
        idxs = np.arange(len(self.data))
        if self.shuffle:
            self.rng.shuffle(idxs)

        for k in idxs:
            yield self.data[k]

class RandomZData(DataFlow):
    """Random dataflow.

    Args:
        shape(tuple): Shape of the array to return on :meth:`get_data`

    """

    def __init__(self, shape):
        """Initialize object."""
        super(RandomZData, self).__init__()
        self.shape = shape

    def get_data(self):
        """Yield random normal vectors of shape :attr:`shape`."""
        while True:
            yield [np.random.normal(0, 1, size=self.shape)]


class MultiModalNumberTransformer:
    r"""Reversible transform for multimodal data.

    To effectively sample values from a multimodal distribution, we cluster values of a
    numerical variable using a `skelarn.mixture.GaussianMixture`_ model (GMM).

    * We train a GMM with :attr:`n` components for each numerical variable :math:`C_i`.
      GMM models a distribution with a weighted sum of :attr:`n` Gaussian distributions.
      The means and standard deviations of the :attr:`n` Gaussian distributions are
      :math:`{\eta}^{(1)}_{i}, ..., {\eta}^{(n)}_{i}` and
      :math:`{\sigma}^{(1)}_{i}, ...,{\sigma}^{(n)}_{i}`.

    * We compute the probability of :math:`c_{i,j}` coming from each of the :attr:`n` Gaussian
      distributions as a vector :math:`{u}^{(1)}_{i,j}, ..., {u}^{(n)}_{i,j}`. u_{i,j} is a
      normalized probability distribution over :attr:`n` Gaussian distributions.

    * We normalize :math:`c_{i,j}` as :math:`v_{i,j} = (c_{i,j}−{\eta}^{(k)}_{i})/2{\sigma}^
      {(k)}_{i}`, where :math:`k = arg max_k {u}^{(k)}_{i,j}`. We then clip :math:`v_{i,j}` to
      [−0.99, 0.99].

    Then we use :math:`u_i` and :math:`v_i` to represent :math:`c_i`. For simplicity,
    we cluster all the numerical features, i.e. both uni-modal and multi-modal features are
    clustered to :attr:`n = 5` Gaussian distributions.

    The simplification is fair because GMM automatically weighs :attr:`n` components.
    For example, if a variable has only one mode and fits some Gaussian distribution, then GMM
    will assign a very low probability to :attr:`n − 1` components and only 1 remaining
    component actually works, which is equivalent to not clustering this feature.

    Args:
        num_modes(int): Number of modes on given data.

    Attributes:
        num_modes(int): Number of components in the `skelarn.mixture.GaussianMixture`_ model.

    .. _skelarn.mixture.GaussianMixture: https://scikit-learn.org/stable/modules/generated/
        sklearn.mixture.GaussianMixture.html

    """

    def __init__(self, num_modes=5):
        """Initialize instance."""
        self.num_modes = num_modes

    @check_inputs
    def transform(self, data):
        """Cluster values using a `skelarn.mixture.GaussianMixture`_ model.

        Args:
            data(numpy.ndarray): Values to cluster in array of shape (n,1).

        Returns:
            tuple[numpy.ndarray, numpy.ndarray, list, list]: Tuple containg the features,
            probabilities, averages and stds of the given data.

        .. _skelarn.mixture.GaussianMixture: https://scikit-learn.org/stable/modules/generated/
            sklearn.mixture.GaussianMixture.html

        """
        model = GaussianMixture(self.num_modes)
        model.fit(data)

        means = model.means_.reshape((1, self.num_modes))
        stds = np.sqrt(model.covariances_).reshape((1, self.num_modes))

        features = (data - means) / (2 * stds)
        probs = model.predict_proba(data)
        argmax = np.argmax(probs, axis=1)
        idx = np.arange(len(features))
        features = features[idx, argmax].reshape([-1, 1])

        features = np.clip(features, -0.99, 0.99)

        return features, probs, list(means.flat), list(stds.flat)

    def reverse_transform(self, data, info):
        """Reverse the clustering of values.

        Args:
            data(numpy.ndarray): Transformed data to restore.
            info(dict): Metadata.

        Returns:
           numpy.ndarray: Values in the original space.

        """
        features = data[:, 0]
        probs = data[:, 1:]
        p_argmax = np.argmax(probs, axis=1)

        mean = np.asarray(info['means'])
        std = np.asarray(info['stds'])

        select_mean = mean[p_argmax]
        select_std = std[p_argmax]

        return features * 2 * select_std + select_mean


class CategoricalTransformer:
    """One-hot encoder for Categorical transformer."""

    def transform(self, data):
        """Apply transform.

        Args:
            data(numpy.ndarray): Categorical array to transform.

        Return:
            tuple[numpy.ndarray, list, int]: Transformed values, list of unique values,
            and amount of uniques.

        """
        unique_values = np.unique(data).tolist()
        value_mapping = {value: index for index, value in enumerate(unique_values)}

        v = list(map(lambda x: value_mapping[x], data))
        features = np.asarray(v).reshape([-1, 1])

        return features, unique_values, len(unique_values)

    @check_inputs
    def reverse_transform(self, data, info):
        """Reverse the transform.

        Args:
            data(np.ndarray): Transformed data to restore as categorical.
            info(dict): Metadata for the given column.

        Returns:
            list: Values in the original space.

        """
        id2str = dict(enumerate(info['mapping']))
        return list(map(lambda x: id2str[x], data.flat))


def split_csv(csv_filename, csv_out1, csv_out2, ratio=0.8):
    """Split a csv file in two and save it.

    Args:
        csv_filename(str): Path for the original file.
        csv_out1(str): Destination for one of the splitted files.
        csv_out2(str): Destination for one of the splitted files.
        ratio(float): Size proportion to split the original file.

    Returns:
        None

    """
    df = pd.read_csv(csv_filename, header=-1)
    mask = np.random.rand(len(df)) < ratio
    df1 = df[mask]
    df2 = df[~mask]
    df1.to_csv(csv_out1, header=False, index=False)
    df2.to_csv(csv_out2, header=False, index=False)


def csv_to_npz(csv_filename, npz_filename, continuous_cols):
    """Read data from a csv file and convert it to the training npz for TGAN.

    Args:
        csv_filename(str): Path to origin csv file.
        npz_filename(str): Path to store the destination npz file.
        continuous_cols(list[str or int]): List of labels for columns with continous values.

    Returns:
        None

    """
    df = pd.read_csv(csv_filename, header=-1)
    num_cols = len(list(df))

    data = {}
    details = []
    continous_transformer = MultiModalNumberTransformer()
    categorical_transformer = CategoricalTransformer()

    for i in range(num_cols):
        if i in continuous_cols:
            column_data = df[i].values.reshape([-1, 1])
            features, probs, means, stds = continous_transformer.transform(column_data)
            details.append({
                "type": "value",
                "means": means,
                "stds": stds,
                "n": 5
            })
            data['f%02d' % i] = np.concatenate((features, probs), axis=1)

        else:
            column_data = df[i].astype(str).values
            features, mapping, n = categorical_transformer.transform(column_data)
            data['f%02d' % i] = features
            details.append({
                "type": "category",
                "mapping": mapping,
                "n": n
            })

    info = {
        "num_features": num_cols,
        "details": details
    }

    np.savez(npz_filename, info=json.dumps(info), **data)


def npz_to_csv(npfilename, csvfilename):
    """Convert a npz file into a csv and return its contents.

    Args:
        npfilename(str): Path to origin npz file.
        csvfilename(str): Path to destination csv file.

    Returns:
        None

    """
    data = np.load(npfilename)
    metadata = json.loads(str(data['info']))
    check_metadata(metadata)

    table = []
    continous_transformer = MultiModalNumberTransformer()
    categorical_transformer = CategoricalTransformer()

    for i in range(metadata['num_features']):
        column_data = data['f%02d' % i]
        column_metadata = metadata['details'][i]

        if column_metadata['type'] == 'value':
            column = continous_transformer.reverse_transform(column_data, column_metadata)

        if column_metadata['type'] == 'category':
            column = categorical_transformer.reverse_transform(column_data, column_metadata)

        table.append(column)

    df = pd.DataFrame(dict(enumerate(table)))
    df.to_csv(csvfilename, index=False, header=False)


class Preprocessor:
    """Transform back and forth human-readable data into TGAN numerical features."""

    def __init__(self, continuous_columns=None, metadata=None):

        if continuous_columns is None:
            continuous_columns = []

        self.continuous_columns = continuous_columns
        self.metadata = metadata
        self.continous_transformer = MultiModalNumberTransformer()
        self.categorical_transformer = CategoricalTransformer()

    def fit_transform(self, data, fitting=True):
        """ """
        num_cols = data.shape[1]

        transformed_data = {}
        details = []

        for i in range(num_cols):
            if i in self.continuous_columns:
                column_data = data[i].values.reshape([-1, 1])
                features, probs, means, stds = self.continous_transformer.transform(column_data)
                details.append({
                    "type": "value",
                    "means": means,
                    "stds": stds,
                    "n": 5
                })
                transformed_data['f%02d' % i] = np.concatenate((features, probs), axis=1)

            else:
                column_data = data[i].astype(str).values
                features, mapping, n = self.categorical_transformer.transform(column_data)
                transformed_data['f%02d' % i] = features
                details.append({
                    "type": "category",
                    "mapping": mapping,
                    "n": n
                })

        if fitting:
            self.metadata = {
                "num_features": num_cols,
                "details": details
            }

        return transformed_data

    def transform(self, data):
        return self.fit_transform(data, fitting=False)

    def fit(self, data):
        self.fit_transform(data)

    def reverse_transform(self, data):

        table = []

        for i in range(self.metadata['num_features']):
            column_data = data['f%02d' % i]
            column_metadata = self.metadata['details'][i]

            if column_metadata['type'] == 'value':
                column = self.continous_transformer.reverse_transform(column_data, column_metadata)

            if column_metadata['type'] == 'category':
                column = self.categorical_transformer.reverse_transform(
                    column_data, column_metadata)

            table.append(column)

        return pd.DataFrame(dict(enumerate(table)))


class TGANDataset:

    def __init__(self, data, preprocessor):
        self.data = data
        self.preprocessor = preprocessor
        self.metadata = preprocessor.metadata
        self.dataflow = NpDataFlow(self.data, self.metadata)

    def get_items(self):
        return self.metadata, self.dataflow



S3_DATASETS = []

def download_dataset():
    pass


def load_data(dataset_name, continuous_columns=None, header=None, preprocessing=True, metadata=None):
    """Load a TGANDataset."""

    if dataset_name in S3_DATASETS:
        raw_dataset = download_dataset(dataset_name)

    else:
        raw_dataset = pd.read_csv(dataset_name, header=header)

    prep = Preprocessor()
    if preprocessing:
        dataset = prep.fit_transform(raw_dataset)

    else:
        prep.metadata = metadata
        dataset = raw_dataset

    return TGANDataset(dataset, prep)