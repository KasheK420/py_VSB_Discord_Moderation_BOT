def instance_dump(instance):
    if instance is None:
        return "None"
    if type(instance) is str:
        return f'"{instance}"'
    if type(instance) is int or type(instance) is float:
        return str(instance)

    source = (
        instance.__slots__
        if hasattr(instance, "__slots__")
        else instance.__dict__
        if hasattr(instance, "__dict__")
        else []
    )
    source = filter(lambda x: not x.startswith("_"), source)
    return f"{{{', '.join([f'{x} = {instance_dump(__get_attribute(instance, x))}' for x in source])}}}"


def __get_attribute(instance, attr):
    if instance is None:
        return None
    try:
        return getattr(instance, attr)
    except AttributeError:
        return f"Error: {attr} not found"
