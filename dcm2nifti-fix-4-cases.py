import os
import sys
import ast
import json
import time
import argparse
import traceback
import hashlib
import numpy as np
import pandas as pd
import pydicom
from tqdm import tqdm
from rt_utils import RTStructBuilder
import SimpleITK as sitk


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

uncleaned_organ_json = 'uncleaned_organ.json'
with open(uncleaned_organ_json,'r') as f:
    UNCLEANED_ORGAN_ENUM_DICT = json.loads(f.read())

with open("organ_mapper.json",'r') as f:
    ORGAN_MAPPER = json.loads(f.read())
dcmdump_csv = 'retry-4-cases.csv'

DICOM_ROOT = '/mnt/hd2/data/ped-ct-seg'

def myjob(outputdir,PatientName,patch_rt):
    df = pd.read_csv(dcmdump_csv)
    
    subject_folder_path = os.path.join(outputdir,PatientName)
    os.makedirs(subject_folder_path,exist_ok=True)
    image_file = os.path.join(subject_folder_path,'image.nii.gz')
    mask_preprocessed_file = os.path.join(subject_folder_path,'mask_preprocessed.nii.gz')
    print(os.path.exists(image_file),image_file)
    print(os.path.exists(mask_preprocessed_file),mask_preprocessed_file)
    print('will attempt to generate above...')

    rt = df[(df["PatientID"]==PatientName)&(df.Modality=="RTSTRUCT")].reset_index()
    ds = df[(df["PatientID"]==PatientName)&(df.Modality=="CT")].reset_index()
    if len(rt)!=1 or len(ds)!=1:
        print(f'missing? {PatientName} rt {len(rt)} ds {len(ds)}')
        return #continue

    ds_folder_path = os.path.join(DICOM_ROOT,ds.SeriesInstanceUID[0])
    rt_folder = os.path.join(DICOM_ROOT,rt.SeriesInstanceUID[0])
    rt_file = os.path.join(rt_folder,os.listdir(rt_folder)[0])
    
    print('ds_folder_path',ds_folder_path)
    print('rt_file',rt_file)
    rt = pydicom.dcmread(rt_file)
    ReferencedSOPInstanceUID_list = [x[(0x0008,0x1155)].value for x in rt[(0x3006,0x0010)][0][(0x3006,0x0012)][0][(0x3006,0x0014)][0][(0x3006,0x0016)]]
    
    SOPInstanceUID_list = []
    for basename in os.listdir(ds_folder_path):
        ds_file = os.path.join(ds_folder_path,basename)
        SOPInstanceUID = pydicom.dcmread(ds_file)['SOPInstanceUID'].value
        SOPInstanceUID_list.append(SOPInstanceUID)

    no_match_list = []
    for ReferencedSOPInstanceUID in ReferencedSOPInstanceUID_list:
        if ReferencedSOPInstanceUID not in SOPInstanceUID_list:
            no_match_list.append(ReferencedSOPInstanceUID)

    if patch_rt:
        print('in 3 seconds we will patch RT_STRUCT!')
        time.sleep(5)
        rt = pydicom.dcmread(rt_file)
        tmp = rt[(0x3006,0x0010)][0][(0x3006,0x0012)][0][(0x3006,0x0014)][0][(0x3006,0x0016)]
        new_list = []
        for x in tmp:
            if x[(0x0008,0x1155)].value in SOPInstanceUID_list:
                new_list.append(x)
        rt[(0x3006,0x0010)][0][(0x3006,0x0012)][0][(0x3006,0x0014)][0][(0x3006,0x0016)].value=new_list
        rt_file = '/tmp/newfile.dcm'
        pydicom.dcmwrite(rt_file, rt,write_like_original=True)
        rt = pydicom.dcmread(rt_file)
        ReferencedSOPInstanceUID_list = [x[(0x0008,0x1155)].value for x in rt[(0x3006,0x0010)][0][(0x3006,0x0012)][0][(0x3006,0x0014)][0][(0x3006,0x0016)]]
        no_match_list = []
        for ReferencedSOPInstanceUID in ReferencedSOPInstanceUID_list:
            if ReferencedSOPInstanceUID not in SOPInstanceUID_list:
                no_match_list.append(ReferencedSOPInstanceUID)

    if len(no_match_list)>0:
        print(len(no_match_list),len(ReferencedSOPInstanceUID_list),len(SOPInstanceUID_list))
        raise ValueError('no matching SOPInstanceUID_list')

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
        print('ds_folder_path',ds_folder_path)
        print('rt_file',rt_file)
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

        print(f'image shape {image.shape}')
        for roi_name in rtstruct.get_roi_names():
            try:
                mask_3d = rtstruct.get_roi_mask_by_name(roi_name)
                print(f"mask_3d {mask_3d.shape}")
                mask_3d = np.swapaxes(mask_3d, 1, 2)
                mask_3d = np.swapaxes(mask_3d, 0, 1)
                target_value = ORGAN_MAPPER[roi_name]
                mask[mask_3d>0] = target_value

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

    return True
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('outputdir')
    parser.add_argument('PatientName')
    parser.add_argument('-p', '--patch_rt',action='store_true')
    args = parser.parse_args()
    myjob(args.outputdir,args.PatientName,args.patch_rt)

"""
use below to locate 4 cases that dcm2nifti.py errored out on.
>>> df=pd.read_csv('image-mask-list.csv')
>>> a=os.listdir('/mnt/hd2/data/ped-ct-seg-nifti')
>>> set(a)-set(df.PatientName)
{'Pediatric-CT-SEG-272B6C5D', 'Pediatric-CT-SEG-CAB73EEC', 'Pediatric-CT-SEG-34ECBB32', 'Pediatric-CT-SEG-14403912'}


below resolved
python dcm2nifti-fix-4-cases.py /mnt/hd2/data/ped-ct-seg-nifti Pediatric-CT-SEG-14403912

below NOT resolved. (add -p to arg!)

python dcm2nifti-fix-4-cases.py /mnt/hd2/data/ped-ct-seg-nifti Pediatric-CT-SEG-272B6C5D
python dcm2nifti-fix-4-cases.py /mnt/hd2/data/ped-ct-seg-nifti Pediatric-CT-SEG-CAB73EEC
python dcm2nifti-fix-4-cases.py /mnt/hd2/data/ped-ct-seg-nifti Pediatric-CT-SEG-34ECBB32




"""