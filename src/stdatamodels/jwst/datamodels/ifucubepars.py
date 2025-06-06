from .reference import ReferenceFileModel

__all__ = ["NirspecIFUCubeParsModel", "MiriIFUCubeParsModel"]


class NirspecIFUCubeParsModel(ReferenceFileModel):
    """
    A data model for Nirspec ifucubepars reference files.

    Attributes
    ----------
    ifucubepars_table : numpy table
         default IFU cube  parameters table
    ifucubepars_msm_table : numpy table
         default IFU cube msm parameters table
    ifucubepars_prism_msm_wavetable : numpy table
         default IFU cube prism msm wavetable
    ifucubepars_med_msm_wavetable : numpy table
         default IFU cube med resolution msm  wavetable
    ifucubepars_high_msm_wavetable : numpy table
         default IFU cube high resolution msm wavetable
    ifucubepars_emsm_table : numpy table
         default IFU cube emsm parameters table
    ifucubepars_prism_emsm_wavetable : numpy table
         default IFU cube prism emsm wavetable
    ifucubepars_med_emsm_wavetable : numpy table
         default IFU cube med resolution emsm wavetable
    ifucubepars_high_emsm_wavetable : numpy table
         default IFU cube high resolution emsm  wavetable
    ifucubepars_prism_driz_wavetable : numpy float32 array
         default IFU cube prism drizzle wavetable
    ifucubepars_med_driz_wavetable : numpy float32 array
         default IFU cube med resolution drizzle wavetable
    ifucubepars_high_driz_wavetable : numpy float32 array
         default IFU cube high resolution drizzle wavetable
    """

    schema_url = "http://stsci.edu/schemas/jwst_datamodel/nirspec_ifucubepars.schema"


class MiriIFUCubeParsModel(ReferenceFileModel):
    """
    A data model for MIRI mrs ifucubepars reference files.

    Attributes
    ----------
    ifucubepars_table : numpy table
         default IFU cube  parameters table
    ifucubepars_msm_table : numpy table
         default IFU cube msm parameters table
    ifucubepars_multichannel_msm_wavetable : numpy table
         default IFU cube msm wavetable
    ifucubepars_emsm_table : numpy table
         default IFU cube emsm parameters table
    ifucubepars_multichannel_emsm_wavetable : numpy table
         default IFU cube emsm wavetable
    ifucubepars_multichannel_driz_wavetable : numpy float32 array
         default IFU cube driz wavetable
    """

    schema_url = "http://stsci.edu/schemas/jwst_datamodel/miri_ifucubepars.schema"
