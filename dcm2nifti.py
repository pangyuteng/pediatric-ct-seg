#
# asyncio following https://kimmosaaskilahti.fi/blog/2021-01-03-asyncio-workers/
#
import os
import sys
import ast
import json
import time
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

# let's take a look at the dicom tags
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
            if ds.Modality == "RTSTRUCT":
                organ_list = [x[(0x3006, 0x0085)].value for x in ds[(0x3006, 0x0080)]]
                myitem['organ_list']=organ_list
            
            mylist.append(myitem)
            print(myitem)
        except:
            traceback.print_exc()
        df = pd.DataFrame(mylist).to_csv(dcmdump_csv,index=False)

uncleaned_organ_json = 'uncleaned_organ.json'
if not os.path.exists(uncleaned_organ_json):
    df = pd.read_csv(dcmdump_csv)
    mylist = []
    [mylist.extend(ast.literal_eval(x)) for x in df.organ_list if isinstance(x,str)]
    mylist = sorted(list(set(mylist)))
    UNCLEANED_ORGAN_ENUM_DICT = {name:n+1 for n,name in enumerate(mylist)}
    with open(uncleaned_organ_json,'w') as f:
        f.write(json.dumps(UNCLEANED_ORGAN_ENUM_DICT))

with open(uncleaned_organ_json,'r') as f:
    UNCLEANED_ORGAN_ENUM_DICT = json.loads(f.read())
print(UNCLEANED_ORGAN_ENUM_DICT)


import asyncio
import concurrent
import threading
MAX_WORKERS = 4
_shutdown = False

def myjob(PatientName):
    if _shutdown:
        print(f"Thread {threading.current_thread().name}: Skipping task {PatientName} as shutdown was requested")
    print(f"Thread {threading.current_thread().name}: Starting task: {PatientName}...")
    df = pd.read_csv(dcmdump_csv)
    
    subject_folder_path = os.path.join(outputdir,PatientName)
    os.makedirs(subject_folder_path,exist_ok=True)
    image_file = os.path.join(subject_folder_path,'image.nii.gz')
    mask_preprocessed_file = os.path.join(subject_folder_path,'mask_preprocessed.nii.gz')

    rt = df[(df["Patient's Name"]==PatientName)&(df.Modality=="RTSTRUCT")].reset_index()
    ds = df[(df["Patient's Name"]==PatientName)&(df.Modality=="CT")].reset_index()
    if len(rt)!=1 or len(ds)!=1:
        print(f'missing? {PatientName}')
        return #continue

    ds_folder_path = os.path.dirname(ds.at[0,'sample_file'])
    rt_file = rt.at[0,'sample_file']

    if not os.path.exists(image_file):

        dcm_list = []
        for x in os.listdir(ds_folder_path):
            dcm_file = os.path.join(ds_folder_path,x)
            ds = pydicom.dcmread(dcm_file,stop_before_pixels=True)
            dcm_list.append([ds.InstanceNumber,dcm_file])

        dcm_list = sorted(dcm_list,key=lambda x: x[0])
        dicom_names = [x[1] for x in dcm_list]
        dicom_names = dicom_names

        reader = sitk.ImageSeriesReader()
        reader.SetFileNames(dicom_names)
        img_obj = reader.Execute()
        image = sitk.GetArrayFromImage(img_obj)
        spacing = img_obj.GetSpacing()
        origin = img_obj.GetOrigin()
        direction = img_obj.GetDirection() 
    
        writer = sitk.ImageFileWriter()
        writer.SetFileName(image_file)
        writer.SetUseCompression(True)
        writer.Execute(img_obj)

    if not os.path.exists(mask_preprocessed_file):

        try:
            rtstruct = RTStructBuilder.create_from(
                dicom_series_path=ds_folder_path, 
                rt_struct_path=rt_file,
            )
        except:
            traceback.print_exc()
            return #continue
                    
        reader= sitk.ImageFileReader()
        reader.SetFileName(image_file)
        img_obj = reader.Execute()
        image = sitk.GetArrayFromImage(img_obj)
        mask = np.zeros_like(image)

        UNCLEANED_ORGAN_ENUM_DICT
        print(f'image shape {image.shape}')
        for roi_name in rtstruct.get_roi_names():
            try:
                mask_3d = rtstruct.get_roi_mask_by_name(roi_name)
                print(f"mask_3d {mask_3d.shape}")
                mask_3d = np.swapaxes(mask_3d, 1, 2)
                mask_3d = np.swapaxes(mask_3d, 0, 1)
                mask[mask_3d>0]=UNCLEANED_ORGAN_ENUM_DICT[roi_name]
            except:
                traceback.print_exc()
                print(roi_name,'!!!')
                
        print(mask.shape,np.unique(mask))
        mask = mask.astype(np.uint8)
        mask = mask[::-1,:,:] #? unsure if this is ok?
        mask_obj = sitk.GetImageFromArray(mask)
        mask_obj.SetSpacing(img_obj.GetSpacing())
        mask_obj.SetOrigin(img_obj.GetOrigin())
        mask_obj.SetDirection(img_obj.GetDirection() )
        writer = sitk.ImageFileWriter()    
        writer.SetFileName(mask_preprocessed_file)
        writer.SetUseCompression(True)
        writer.Execute(mask_obj)

    print(f"Thread {threading.current_thread().name}: Finished task {PatientName}!")
    return True

# locate files and store as nifti
main_csv = 'image-mask-list.csv'
if not os.path.exists(main_csv):

    df = pd.read_csv(dcmdump_csv)
    patient_list = list(df["Patient's Name"].unique())
    
    async def mymain():
        global _shutdown
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            loop = asyncio.get_running_loop()
            futures = [
                loop.run_in_executor(pool, myjob, x) for x in patient_list
            ]
            try:
                results = await asyncio.gather(*futures, return_exceptions=False)
            except Exception as ex:
                #traceback.print_exc()
                print("Caught error executing task", ex)
                _shutdown = True
                raise
        return results
    stime = time.time()
    asyncio.run(mymain())
    etime = time.time()
    print(etime-stime)
    

    mylist = []
    for PatientName in tqdm(df["Patient's Name"].unique()):

        subject_folder_path = os.path.join(outputdir,PatientName)
        os.makedirs(subject_folder_path,exist_ok=True)
        image_file = os.path.join(subject_folder_path,'image.nii.gz')
        mask_preprocessed_file = os.path.join(subject_folder_path,'mask_preprocessed.nii.gz')

        if not os.path.exists(image_file) or \
            not os.path.exists(mask_preprocessed_file):
            continue
            
        item = dict(
            PatientName=PatientName,
            image_file=image_file,
            mask_preprocessed_file=mask_preprocessed_file,
        )
        mylist.append(item)
        pd.DataFrame(mylist).to_csv(main_csv,index=False)
    