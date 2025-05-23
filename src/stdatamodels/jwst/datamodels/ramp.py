from .model_base import JwstDataModel


__all__ = ["RampModel"]


class RampModel(JwstDataModel):
    """
    A data model for 4D ramps.

    Attributes
    ----------
    data : numpy float32 array
         The science data
    pixeldq : numpy uint32 array
         2-D data quality array for all planes
    groupdq : numpy uint8 array
         4-D data quality array for each plane
    zeroframe : numpy float32 array
         Zeroframe array
    group : numpy table
         group parameters table
    int_times : numpy table
         table of times for each integration
    """

    schema_url = "http://stsci.edu/schemas/jwst_datamodel/ramp.schema"

    def __init__(self, init=None, **kwargs):
        super(RampModel, self).__init__(init=init, **kwargs)

        # Implicitly create arrays
        self.pixeldq = self.pixeldq
        self.groupdq = self.groupdq
