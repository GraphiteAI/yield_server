def orm_to_dict(obj, table_mapping=None):
    if table_mapping is None:
        table_mapping = obj.__table__
    return {c.name: getattr(obj, c.name) for c in table_mapping.columns}