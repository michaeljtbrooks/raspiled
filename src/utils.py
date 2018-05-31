def Odict2int(ODict):
    '''
    Converts an OrderedDict with unicode values to integers (port and pins).
    @param Odict: <OrderedDict> containg RASPILED configuration.

    @returns: <OrderedDict> with integers instead of unicode values.
    '''
    for key,value in ODict.items():
        try:
            ODict[key]=int(value)
        except:
            pass
    return ODict
