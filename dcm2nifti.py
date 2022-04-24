

import os
import sys
import traceback
import hashlib
import numpy as np
import pandas as pd
import pydicom
from tqdm import tqdm
from rt_utils import RTStructBuilder
import SimpleITK as sitk

inputdir = sys.argv[1]
outputdir = sys.argv[2]
print(inputdir)
print(outputdir)

skip = [
    "De-identification Method",
    "De-identification Method Code Sequence",
    "Private Creator",
    "Private tag data",
    "Private tag data",
    "Longitudinal Temporal Information Modified",
    "Structure Set Label",
    "Structure Set Name",
    "Structure Set Date",
    "Structure Set Time",
    "Referenced Frame of Reference Sequence",
    "Structure Set ROI Sequence",
    "ROI Contour Sequence",
    "RT ROI Observations Sequence",
    "Approval Status",
    "Specific Character Set",    
    "Coding Scheme Identification Sequence",
    "Context Group Identification Sequence",
    "Mapping Resource Identification Sequence",
    "Patient Identity Removed",
]

# let take a look at the dicom tags
dcmdump_csv = "dcmdump.csv"
if not os.path.exists(dcmdump_csv):

    mylist = []
    for x in tqdm(os.listdir(inputdir)):
        folder_path = os.path.join(inputdir,x)
        file_list = sorted([os.path.join(folder_path,x) for x in os.listdir(folder_path)])
        sample_file = file_list[0]        
        try:
            ds = pydicom.dcmread(sample_file,stop_before_pixels=True)
            myitem = {e.name:str(e.value) for e in ds if e.name not in skip}
            myitem['sample_file']=sample_file
            mylist.append(myitem)
            print(myitem)
        except:
            traceback.print_exc()
    df = pd.DataFrame(mylist).to_csv(dcmdump_csv,index=False)

