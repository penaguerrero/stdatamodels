# Licensed under a 3-clause BSD style license - see LICENSE.rst

import copy
import numpy as np
from collections.abc import Mapping
from astropy.io import fits

from asdf.tags.core import ndarray

from . import util
from . import validate
from . import schema as mschema

import logging

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


__all__ = ["ObjectNode", "ListNode"]


def _is_struct_array(val):
    return (
        isinstance(val, (np.ndarray, fits.FITS_rec))
        and val.dtype.names is not None
        and val.dtype.fields is not None
    )


def _is_struct_array_precursor(val):
    return isinstance(val, list) and isinstance(val[0], tuple)


def _is_struct_array_schema(schema):
    return isinstance(schema["datatype"], list) and any("name" in t for t in schema["datatype"])


def _cast(val, schema):
    val = _unmake_node(val)
    if val is None:
        return None

    if "datatype" in schema:
        # Handle lazy array
        if isinstance(val, ndarray.NDArrayType):
            val = val._make_array()

        allow_extra_columns = False
        if (
            _is_struct_array_schema(schema)
            and len(val)
            and (_is_struct_array_precursor(val) or _is_struct_array(val))
        ):
            # we are dealing with a structured array. Because we may
            # modify schema (to add shape), we make a deep copy of the
            # schema here:
            schema = copy.deepcopy(schema)

            if "allow_extra_columns" in schema:
                allow_extra_columns = schema["allow_extra_columns"]

            for t, v in zip(schema["datatype"], val[0], strict=False):
                if not isinstance(t, Mapping):
                    continue

                aval = np.asanyarray(v)
                shape = aval.shape
                val_ndim = len(shape)

                # make sure that if 'ndim' is specified for a field,
                # it matches the dimensionality of val's field:
                if "ndim" in t and val_ndim != t["ndim"]:
                    raise ValueError(
                        "Array has wrong number of dimensions. Expected {}, got {}".format(
                            t["ndim"], val_ndim
                        )
                    )

                if "max_ndim" in t and val_ndim > t["max_ndim"]:
                    raise ValueError(
                        "Array has wrong number of dimensions. Expected <= {}, got {}".format(
                            t["max_ndim"], val_ndim
                        )
                    )

                # if shape of a field's value is not specified in the schema,
                # add it to the schema based on the shape of the actual data:
                if "shape" not in t:
                    t["shape"] = shape

        dtype = ndarray.asdf_datatype_to_numpy_dtype(schema["datatype"])

        # save columns in case this is cast back to a fitsrec
        if hasattr(val, "columns"):
            cols = val.columns
        else:
            cols = None
        val = util.gentle_asarray(val, dtype, allow_extra_columns=allow_extra_columns)

        if dtype.fields is not None:
            val = _as_fitsrec(val)
            if cols is not None:
                for col in cols:
                    if col.name in val.names and col.unit is not None:
                        val.columns[col.name].unit = col.unit

    if "ndim" in schema and len(val.shape) != schema["ndim"]:
        raise ValueError(
            "Array has wrong number of dimensions.  Expected {}, got {}".format(
                schema["ndim"], len(val.shape)
            )
        )

    if "max_ndim" in schema and len(val.shape) > schema["max_ndim"]:
        raise ValueError(
            "Array has wrong number of dimensions.  Expected <= {}, got {}".format(
                schema["max_ndim"], len(val.shape)
            )
        )

    if isinstance(val, np.generic) and np.isscalar(val):
        val = val.item()

    return val


def _as_fitsrec(val):
    """
    Convert a numpy record into a FITS record if it is not one already.

    Parameters
    ----------
    val : numpy.ndarray
        The numpy record to convert.

    Returns
    -------
    fits.FITS_rec
        The converted FITS record.
    """
    if isinstance(val, fits.FITS_rec):
        return val
    else:
        coldefs = fits.ColDefs(val)
        uint = any(c._pseudo_unsigned_ints for c in coldefs)
        fits_rec = fits.FITS_rec(val)
        fits_rec._coldefs = coldefs
        # FITS_rec needs to know if it should be operating in pseudo-unsigned-ints mode,
        # otherwise it won't properly convert integer columns with TZEROn before saving.
        fits_rec._uint = uint
        return fits_rec


def _get_schema_type(schema):
    """
    Find the type or types used by a schema.

    Create a list of types used by a schema and its subschemas when
    the subschemas are joined by combiners. Then return a type string
    if all the types are the same or 'mixed' if they differ.

    Parameters
    ----------
    schema : dict
        The schema to analyze.

    Returns
    -------
    str
        The type used by a schema, or 'mixed' if the schema has multiple types.
    """

    def callback(subschema, path, combiner, types, recurse):
        if "type" in subschema:
            types.append(subschema["type"])

        has_combiner = "anyOf" in subschema.keys() or "allOf" in subschema.keys()
        return not has_combiner

    types = []
    mschema.walk_schema(schema, callback, types)

    schema_type = None
    for a_type in types:
        if schema_type is None:
            schema_type = a_type
        elif schema_type != a_type:
            schema_type = "mixed"
            break

    return schema_type


def _make_default_array(attr, schema, ctx):
    dtype = schema.get("datatype")
    if dtype is not None:
        dtype = ndarray.asdf_datatype_to_numpy_dtype(dtype)
    ndim = schema.get("ndim", schema.get("max_ndim"))
    default = schema.get("default", None)
    primary_array_name = ctx.get_primary_array_name()

    if attr == primary_array_name:
        if ctx.shape is not None:
            shape = ctx.shape
            _validate_primary_shape(schema, shape)
        elif ndim is not None:
            shape = tuple([0] * ndim)
        else:
            shape = (0,)
    else:
        if dtype.names is not None:
            if ndim is None:
                shape = (0,)
            else:
                shape = tuple([0] * ndim)
            default = None
        else:
            has_primary_array_shape = False
            if primary_array_name is not None:
                primary_array = getattr(ctx, primary_array_name, None)
                has_primary_array_shape = primary_array is not None

            if has_primary_array_shape:
                if ndim is None:
                    shape = primary_array.shape
                else:
                    if attr == "zeroframe":
                        dims = primary_array.shape
                        if len(dims) != 4:
                            error_msg = "To allocate ZEROFRAME, the primary array must "
                            error_msg += f"have 4 dimensions, but has {len(dims)}."
                            raise IndexError(error_msg)
                        shape = (dims[0], dims[2], dims[3])
                    else:
                        shape = primary_array.shape[-ndim:]
            elif ndim is None:
                shape = (0,)
            else:
                shape = tuple([0] * ndim)

    array = np.empty(shape, dtype=dtype)
    if default is not None:
        if isinstance(default, list):
            # support multi-valued defaults for when array is recarray
            try:
                default = np.array(tuple(default), dtype=dtype)
            except ValueError:
                msg = f"Invalid default value {default} for recarray dtype {dtype}"
                raise ValueError(msg) from None
        array[...] = default
    return array


def _validate_primary_shape(schema, shape):
    """
    Ensure requested shape is allowed by schema.

    Parameters
    ----------
    schema : dict
        The schema for the primary array.
    shape : tuple
        The requested shape of the default array.

    Raises
    ------
    ValueError
        If the requested has dimensions different from the schema's ndim,
        or larger than the schema's max_ndim.
    """
    ndim_requested = len(shape)
    max_ndim = schema.get("max_ndim", None)
    ndim = schema.get("ndim", None)
    if (ndim is not None) and (ndim_requested != ndim):
        msg = f"Array has wrong number of dimensions. Expected {ndim}, got {ndim_requested}"
        raise ValueError(msg)
    if (max_ndim is not None) and (ndim_requested > max_ndim):
        msg = f"Array has wrong number of dimensions. Expected <= {max_ndim}, got {ndim_requested}"
        raise ValueError(msg)


def _make_default(attr, schema, ctx):
    if "max_ndim" in schema or "ndim" in schema or "datatype" in schema:
        return _make_default_array(attr, schema, ctx)
    elif "default" in schema:
        return schema["default"]
    else:
        schema_type = _get_schema_type(schema)
        if schema_type == "object":
            return {}
        elif schema_type == "array":
            return []
        else:
            return None


def _make_node(attr, instance, schema, ctx, parent):
    if isinstance(instance, dict):
        return ObjectNode(attr, instance, schema, ctx, parent)
    elif isinstance(instance, list):
        return ListNode(attr, instance, schema, ctx, parent)
    else:
        return instance


def _unmake_node(obj):
    if isinstance(obj, Node):
        return obj.instance
    return obj


def _get_schema_for_property(schema, attr):
    subschema = schema.get("properties", {}).get(attr, None)
    if subschema is not None:
        return subschema
    for combiner in ["allOf", "anyOf"]:
        for subschema in schema.get(combiner, []):
            subsubschema = _get_schema_for_property(subschema, attr)
            if subsubschema != {}:
                return subsubschema
    return {}


def _get_schema_for_index(schema, i):
    items = schema.get("items", {})
    if isinstance(items, list):
        if i >= len(items):
            return {}
        else:
            return items[i]
    else:
        return items


def _find_property(schema, attr):
    subschema = _get_schema_for_property(schema, attr)
    if subschema == {}:
        find = False
    else:
        find = "default" in subschema
    return find


class Node:
    """An object that supports validation against a schema."""

    def __init__(self, attr, instance, schema, ctx, parent):
        self._name = attr
        self._instance = instance
        self._schema = schema
        self._ctx = ctx
        self._parent = parent

    def _validate(self):
        return validate.value_change(self._name, self._instance, self._schema, self._ctx)

    @property
    def instance(self):
        return self._instance


class ObjectNode(Node):
    """A dictionary-like Node."""

    def __dir__(self):
        added = set(self._schema.get("properties", {}).keys())
        return sorted(set(super().__dir__()) | added)

    def __eq__(self, other):
        if isinstance(other, ObjectNode):
            return self._instance == other._instance
        else:
            return self._instance == other

    def __getattr__(self, attr):
        if attr.startswith("_"):
            raise AttributeError(f"No attribute {attr}")

        schema = _get_schema_for_property(self._schema, attr)
        try:
            val = self._instance[attr]
        except KeyError as err:
            if schema == {}:
                raise AttributeError(f"No attribute '{attr}'") from err

            val = _make_default(attr, schema, self._ctx)
            if val is not None:
                self._instance[attr] = val

        if isinstance(val, dict):
            node = ObjectNode(attr, val, schema, self._ctx, self)
        elif isinstance(val, list):
            node = ListNode(attr, val, schema, self._ctx, self)
        else:
            node = val

        return node

    def __setattr__(self, attr, val):
        if attr.startswith("_"):
            self.__dict__[attr] = val
        else:
            schema = _get_schema_for_property(self._schema, attr)
            if val is None:
                val = _make_default(attr, schema, self._ctx)
            val = _cast(val, schema)

            node = ObjectNode(attr, val, schema, self._ctx, self)
            if self._ctx._validate_on_assignment:
                if node._validate():
                    self._instance[attr] = val
            else:
                self._instance[attr] = val

    def __delattr__(self, attr):
        if attr.startswith("_"):
            del self.__dict__[attr]
        else:
            schema = _get_schema_for_property(self._schema, attr)
            if (
                validate.value_change(attr, None, schema, self._ctx)
                or self._ctx._pass_invalid_values
            ):
                try:
                    del self._instance[attr]
                except KeyError as err:
                    raise AttributeError(f"Attribute '{attr}' missing") from err

    def __iter__(self):
        return NodeIterator(self)

    def hasattr(self, attr):  # noqa: D102
        return attr in self._instance

    def items(self):  # noqa: D102
        # Return a (key, value) tuple for the node
        for key in self:
            val = self
            for field in key.split("."):
                val = getattr(val, field)
            yield (key, val)


class ListNode(Node):
    """A list-like Node."""

    def __cast(self, other):
        if isinstance(other, ListNode):
            return other._instance
        return other

    def __repr__(self):
        return repr(self._instance)

    def __eq__(self, other):
        return self._instance == self.__cast(other)

    def __ne__(self, other):
        return self._instance != self.__cast(other)

    def __contains__(self, item):
        return item in self._instance

    def __len__(self):
        return len(self._instance)

    def __getitem__(self, i):
        schema = _get_schema_for_index(self._schema, i)
        return _make_node(self._name, self._instance[i], schema, self._ctx, self)

    def __setitem__(self, i, val):
        schema = _get_schema_for_index(self._schema, i)
        val = _cast(val, schema)
        node = ObjectNode(self._name, val, schema, self._ctx, self)
        if self._ctx._validate_on_assignment:
            if node._validate():
                self._instance[i] = val
        else:
            self._instance[i] = val

    def __delitem__(self, i):
        del self._instance[i]
        if self._ctx._validate_on_assignment:
            self._validate()

    def append(self, item):  # noqa: D102
        schema = _get_schema_for_index(self._schema, len(self._instance))
        item = _cast(item, schema)
        node = ObjectNode(self._name, item, schema, self._ctx, self)
        if self._ctx._validate_on_assignment:
            if node._validate():
                self._instance.append(item)
        else:
            self._instance.append(item)

    def insert(self, i, item):  # noqa: D102
        schema = _get_schema_for_index(self._schema, i)
        item = _cast(item, schema)
        node = ObjectNode(self._name, item, schema, self._ctx, self)
        if self._ctx._validate_on_assignment:
            if node._validate():
                self._instance.insert(i, item)
        else:
            self._instance.insert(i, item)

    def pop(self, i=-1):  # noqa: D102
        schema = _get_schema_for_index(self._schema, 0)
        x = self._instance.pop(i)
        return _make_node(self._name, x, schema, self._ctx, self)

    def remove(self, item):  # noqa: D102
        self._instance.remove(item)

    def count(self, item):  # noqa: D102
        return self._instance.count(item)

    def index(self, item):  # noqa: D102
        return self._instance.index(item)

    def reverse(self):  # noqa: D102
        self._instance.reverse()

    def sort(self, *args, **kwargs):  # noqa: D102
        self._instance.sort(*args, **kwargs)

    def extend(self, other):  # noqa: D102
        for part in _unmake_node(other):
            self.append(part)

    def item(self, **kwargs):  # noqa: D102
        assert isinstance(self._schema["items"], dict)
        node = ObjectNode(self._name, kwargs, self._schema["items"], self._ctx, self)
        if not self._ctx._validate_on_assignment:
            return node
        if not node._validate():
            node = None
        return node


class NodeIterator:
    """An iterator for a node which flattens the hierarchical structure."""

    def __init__(self, node):
        self.key_stack = []
        self.iter_stack = [iter(node._instance.items())]

    def __iter__(self):
        return self

    def __next__(self):
        while self.iter_stack:
            try:
                key, val = next(self.iter_stack[-1])
            except StopIteration:
                self.iter_stack.pop()
                if self.iter_stack:
                    self.key_stack.pop()
                continue

            if isinstance(val, dict):
                self.key_stack.append(key)
                self.iter_stack.append(iter(val.items()))
            else:
                return ".".join(self.key_stack + [key])

        raise StopIteration


def put_value(path, value, tree):
    """
    Put a value at the given path into tree, replacing it if it is already present.

    Parameters
    ----------
    path : list of str or int
        The path to the element.
    value : any
        The value to place
    tree : dict
        The tree to place the value into.
    """
    cursor = tree
    for i in range(len(path) - 1):
        part = path[i]
        if isinstance(part, int):
            while len(cursor) <= part:
                cursor.append({})
            cursor = cursor[part]
        else:
            if isinstance(path[i + 1], int) or path[i + 1] == "items":
                cursor = cursor.setdefault(part, [])
            else:
                cursor = cursor.setdefault(part, {})

    if isinstance(path[-1], int):
        while len(cursor) <= path[-1]:
            cursor.append({})
    cursor[path[-1]] = value


def merge_tree(a, b):
    """
    Merge elements from tree `b` into tree `a`.

    Parameters
    ----------
    a : dict
        The tree to merge into.
    b : dict
        The tree to merge from.

    Returns
    -------
    a : dict
        The merged tree.
    """

    def recurse(a, b):
        if isinstance(b, dict):
            if not isinstance(a, dict):
                return copy.deepcopy(b)
            for key, val in b.items():
                a[key] = recurse(a.get(key), val)
            return a
        return copy.deepcopy(b)

    recurse(a, b)
    return a
