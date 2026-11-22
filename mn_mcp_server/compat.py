# -*- coding: utf-8 -*-
"""Small shims so the module reads/writes ``ir.config_parameter`` the same way
on Odoo 19 (``get_param``/``set_param``) and Odoo 20 (typed accessors)."""


def icp_get(icp, key, default=None):
    """Read a system parameter as a string, with a default."""
    if hasattr(icp, "get_param"):
        return icp.get_param(key, default)
    value = icp.get_str(key)
    return value if value not in (None, False, "") else default


def icp_set(icp, key, value):
    """Write a system parameter."""
    if hasattr(icp, "set_param"):
        return icp.set_param(key, value)
    return icp.set_str(key, value)
