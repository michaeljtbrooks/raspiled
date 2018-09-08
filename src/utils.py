
def Odict2int(ODict):
    '''
    Converts an OrderedDict with unicode values to integers and/or floats (port and pins).
    @param Odict: <OrderedDict> containg RASPILED configuration.

    @returns: <OrderedDict> with integers instead of unicode values.
    '''
    for key,value in ODict.items():
        if u"." in unicode(value):
            casting_function = float
        else:
            casting_function = int
        try:
            ODict[key] = casting_function(value)
        except (TypeError, ValueError):
            pass
    return ODict
