def join_non_empty(delimiter, *args):
    """
    join the string representation of all non empty args with delimiter.
    (empty means "" or None)
    """

    return delimiter.join([str(x) for x in args if x is not None and x != ""])
