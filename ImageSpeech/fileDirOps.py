from __future__ import print_function
# this file contains different operations on files and directories:
#   1. fixNames: files generated with old functions give mouth images, stored as 'videoName_faces_frameNb.jpg'
#                Transform this to the format 'videoName_frameNb_faces.jpg'
#
import sys
import getopt
import zipfile, os.path
import concurrent.futures
import threading

import os, errno
import subprocess
import shutil

from helpFunctions import *

# 1. remove all specified directories and their contents
# a rootdir, and a list of dirnames to be removed
# THIS FUNCTION deletes all specified directories AND their contents !!!
# Be careful!
def deleteDirs(rootDir, names):
    dirList= []
    for root, dirs, files in os.walk(rootDir):
        for dirname in dirs:
            for name in names:
                if name in dirname:
                    path = ''.join([root, os.sep, dirname])
                    dirList.append(path)
    print(dirList)
    if query_yes_no("Are you sure you want to delete all these directories AND THEIR CONTENTS under %s?" %rootDir , "yes"):
        nbRemoved = 0
        for dir in dirList:
            print('Deleting dir: %s' % dir)
            shutil.rmtree(dir)
            nbRemoved +=1
        print(nbRemoved, " directories have been deleted")
    return dirList

# stuff for getting relative paths between two directories
def pathsplit(p, rest=[]):
    (h,t) = os.path.split(p)
    if len(h) < 1: return [t]+rest
    if len(t) < 1: return [h]+rest
    return pathsplit(h,[t]+rest)

def commonpath(l1, l2, common=[]):
    if len(l1) < 1: return (common, l1, l2)
    if len(l2) < 1: return (common, l1, l2)
    if l1[0] != l2[0]: return (common, l1, l2)
    return commonpath(l1[1:], l2[1:], common+[l1[0]])

# p1 = main path, p2= the one you want to get the relative path of
def relpath(p1, p2):
    (common,l1,l2) = commonpath(pathsplit(p1), pathsplit(p2))
    p = []
    if len(l1) > 0:
        p = [ '../' * len(l1) ]
    p = p + l2
    return os.path.join( *p )

# 2. copy a dir structure under a new root dir
# copy all mouth files to a new dir, per speaker. Also remove the 'mouths_gray_120' directory, so the files are directly under the videoName folder
# -> processed/lipspeakers

# helpfunction: fix shutil.copytree to allow writing to existing files and directories (http://stackoverflow.com/questions/1868714/how-do-i-copy-an-entire-directory-of-files-into-an-existing-directory-using-pyth#12514470)
def copytree(src, dst, symlinks=False, ignore=None):
    if not os.path.exists(dst):
        os.makedirs(dst)
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            copytree(s, d, symlinks, ignore)
        else:
            if not os.path.exists(d) or os.stat(s).st_mtime - os.stat(d).st_mtime > 1:
                shutil.copy2(s, d)
            
def copyDBFiles(rootDir, names, targetRoot):
    from shutil import copyfile
    dirList = []
    fileList = []
    for root, dirs, files in os.walk(rootDir):
        for dir in dirs:
            for name in names:
                if name in dir:
                    path = ''.join([root, os.sep, dir])
                    dirList.append(path)
        for file in files:
            name, extension = os.path.splitext(file)
            # copy phoneme files as well
            if extension == ".txt":
                path = ''.join([root, os.sep, file])
                fileList.append(path)
    
    print("First 10 files to be copied: ", fileList[0:10])

    if query_yes_no("Are you sure you want to copy all these directories %s to %s?" %(rootDir, targetRoot) , "yes"):
        nbCopiedDirs = 0
        nbCopiedFiles = 0
        
        for dir in dirList:
            relativePath = relpath(rootDir, dir)
            relativePath = relativePath.replace('/mouths_gray_120','')
            dest = ''.join([targetRoot+os.sep+relativePath])
            #print("copying dir:", dir, " to: ", dest)
            copytree(dir, dest)
            nbCopiedDirs +=1
        
        for file in fileList:
            relativePath = relpath(rootDir, file)
            #print("copying file:", file, " to: ", targetRoot+os.sep+relativePath)
            dest = ''.join([targetRoot+os.sep+relativePath])
            copyfile(file, dest)
            nbCopiedFiles +=1
            
        print(nbCopiedDirs, " directories have been copied to ", targetRoot)
        print(nbCopiedFiles, " files have been copied to ", targetRoot)
    return dirList

# extract phonemes for each image, put them in the image name
def addPhonemesToImageNames(videoDir):
    # videoDir will be the lowest-level directory
    videoName = os.path.basename(videoDir)
    parentName = os.path.basename(os.path.dirname(videoDir))
    validFrames = {}
    phonemeFile = ''.join([videoDir + os.sep + parentName + "_" + videoName + "_PHN.txt"])
    #print(phonemeFile)
    with open(phonemeFile) as inf:
        for line in inf:
            parts = line.split()  # split line into parts
            if len(parts) > 1:  # if at least 2 parts/columns
                validFrames[str(parts[0])] = parts[1]  # dict, key= frame, value = phoneme
    nbRenamed = 0
    for root, dirs, files in os.walk(videoDir):
        for file in files:
            fileName, ext = os.path.splitext(file)
            if ext == ".jpg":
                filePath = ''.join([root,os.sep,file])
                videoName = file.split("_")[0]
                frameNumber = file.split("_")[1] #number-> after first underscore
                phoneme = validFrames[frameNumber]
                newFileName = ''.join([videoName, "_", frameNumber, "_", phoneme, ext])
                parent = os.path.dirname(root)
                newFilePath = ''.join([parent, os.sep, newFileName ])
                # print(filePath, " will be renamed to: ", newFilePath)
                os.rename(filePath, newFilePath)
                nbRenamed += 1
            if ext == ".txt":
                filePath = ''.join([root, os.sep, file])
                videoName = file.split("_")[1]
                newFilePath = filePath.replace(videoName+os.sep,'')
                os.rename(filePath, newFilePath)
                
    #print("Finished renaming ", nbRenamed, " files.")
    return 0

# need this to traverse directories, find depth
def directories (root):
    dirList = []
    for path, folders, files in os.walk(root):
        for name in folders:
            dirList.append(os.path.join(path, name))
    return dirList

def depth(path):
    return path.count(os.sep)

# now traverse the database tree and rename  files in all the directories
def addPhonemesToImagesDB(rootDir):
    dirList = []
    for dir in directories(rootDir):
        # print(dir)
        # print(relpath(rootDir,dir))
        # print(depth(relpath(rootDir,dir)))
        if depth(relpath(rootDir, dir)) == 2:
            dirList.append(dir)
    print("First 10 directories to be processed: ", dirList[0:10])
    for dir in dirList:
        addPhonemesToImageNames(dir)
        os.rmdir(dir)
    return 0

# helpfunction
def getPhonemeNumberMap (
        phonemeMap="/home/matthijs/Documents/Dropbox/_MyDocs/_ku_leuven/Master/Thesis/ImageSpeech/phonemeLabelConversion.txt"):
    phonemeNumberMap = {}
    with open(phonemeMap) as inf:
        for line in inf:
            parts = line.split()    # split line into parts
            if len(parts) > 1:      # if at least 2 parts/columns
                phonemeNumberMap[str(parts[0])] = parts[1]  # part0= frame, part1 = phoneme
                phonemeNumberMap[str(parts[1])] = parts[0]
    return phonemeNumberMap

def speakerToBinary(speakerDir, binaryDatabaseDir):
    import numpy as np
    from PIL import Image
    
    rootDir = speakerDir
    targetDir = binaryDatabaseDir
    if not os.path.exists(targetDir):
        os.makedirs(targetDir)
    
    # get list of images and list of labels
    images = []
    labels = []
    for root, dirs, files in os.walk(rootDir):
        for file in files:
            name, extension = os.path.splitext(file)
            # copy phoneme files as well
            if extension == ".jpg":
                videoName, frame, phoneme = name.split("_")
                path = ''.join([root, os.sep, file])
                #print(path, " is \t ", phoneme)
                images.append(path)
                labels.append(phoneme)
    
    # write label and image to binary file, 1 label+image per row
    speakerName = os.path.basename(rootDir)
    output_filename = targetDir + os.sep + speakerName + ".bin"
    
    with open(output_filename,
              "wb") as f:  # from http://stackoverflow.com/questions/38880654/how-do-i-create-a-dataset-with-multiple-images-the-same-format-as-cifar10?rq=1
        for label, img in zip(labels, images):
            phonemeNumberMap = getPhonemeNumberMap()
            labelNumber = phonemeNumberMap[label]
            npLabel = np.array(labelNumber, dtype=np.uint8)
        
            im = np.array(Image.open(img), dtype=np.uint8)
            
            f.write(npLabel.tostring())  # Write label.
            f.write(im[:, :].tostring())  # Write grey channel, it's the only one
    print(speakerName, "files have been written to: ", output_filename)
    return 0

def allSpeakersToBinary(databaseDir, binaryDatabaseDir):
    rootDir = databaseDir
    dirList = []
    for dir in directories(rootDir):
        # print(dir)
        # print(relpath(rootDir, dir))
        # print(depth(relpath(rootDir, dir)))
        if depth(relpath(rootDir, dir)) == 1:
            dirList.append(dir)
    print(dirList)
    for speakerDir in dirList:
        speakerToBinary(speakerDir, binaryDatabaseDir)
    return 0
        
        
        
if __name__ == "__main__":

    # use this to copy the grayscale files from 'processDatabase' to another location, and fix their names with phonemes
    # then convert to files useable by CIFAR10 code
    
    processedDir = "/home/matthijs/TCDTIMIT/processed"
    databaseDir = "/home/matthijs/TCDTIMIT/database"
    databaseBinaryDir = "/home/matthijs/TCDTIMIT/database_binary"
    
    # 1. copy mouths_gray_120 images and PHN.txt files to targetRoot. Move files up from their mouths_gray_120 dir to the video dir (eg sa1)
    print("Copying mouth_gray_120 directories to database location...")
    copyDBFiles(processedDir, ["mouths_gray_120"], databaseDir)
    print("-----------------------------------------")
    
    # 2. extract phonemes for each image, put them in the image name
    # has to be called against the 'database' directory
    print("Adding phoneme to filenames, moving files up to speakerDir...")
    addPhonemesToImagesDB(databaseDir)
    print("-----------------------------------------")

    # 3. convert all files from one speaker to a a binary file in CIFAR10 format:
    # each row = label + image
    # this function has to be called against the 'database' directory
    print("Copying the labels and images into binary CIFAR10 format...")
    allSpeakersToBinary(databaseDir, databaseBinaryDir)
    print("The final binary files can be found in: ", databaseBinaryDir)
    print("-----------------------------------------")
    
    
    # Other functions that are not normally needed
    # 1. deleting directories, not needed
    # root = "/home/matthijs/TCDTIMIT2/processed"
    # name = ["mouths", "faces"]
    # deleteDirs(root, name)



############ OUTDATED ###############
# Normally you don't need this functions anymore. They are here just for reference

# Some files were badly named; fix names so we can use them for training
def fixNames (rootDir):
    nbRenames = 0
    # step 1: Change names so that the 'faces' string is at the end of the filename, and it looks like: 'videoName_frameNb_faces.jpg'
    for root, dirs, files in os.walk(rootDir):
        files.sort(key=tryint)
        for file in files:
            if "face" in file:  # sanity check
                filePath = os.path.join(root, file)
                parentDir = os.path.dirname(root)
                fname = os.path.splitext(os.path.basename(file))[0]
                videoName, facestr, frame = fname.split("_")
                if facestr == "face":  # if faces in the middle, swap frameNb and facestr
                    fileNew = ''.join([videoName, "_", frame, "_", facestr, ".jpg"])
                    fileNewPath = ''.join([root, fileNew])
                    fileNewPath = os.path.join(root, fileNew)
                    print(filePath + "\t -> \t" + fileNewPath)
                    # os.rename(filePath, fileNewPath)
                    nbRenames += 1
    
    # Step 2: names are in proper format, now move to mouths folder (because the images contain mouths, not faces)
    nbMoves = 0
    for root, dirs, files in os.walk(rootDir):
        files.sort(key=tryint)
        for file in files:
            
            if "face" in file:  # sanity check
                filePath = os.path.join(root, file)
                parentDir = os.path.dirname(root)
                fname = os.path.splitext(os.path.basename(file))[0]
                videoName, frame, facestr = fname.split("_")
                fileNew = ''.join([videoName, "_", frame, "_mouth.jpg"])  # replace 'face' with 'mouth'
                mouthsDir = ''.join([parentDir, os.sep, "mouths"])
                if not os.path.exists(mouthsDir):
                    os.makedirs(mouthsDir)
                fileNewPath = ''.join([mouthsDir, os.sep, fileNew])
                print(filePath + "\t -> \t" + fileNewPath)
                # os.rename(filePath, fileNewPath)
                nbMoves += 1
    
    print(nbRenames, " files have been renamed.")
    print(nbMoves, "files have been moved.")
    return 0


# example usage
# root = "/home/matthijs/TCDTIMIT/processed2"
# fixNames(root)



# convert from frame number to timing info. I didn't need this as I worked with frames all the time
from shutil import copyfile


def frameToTiming (rootDir):
    nbCopies = 0
    for root, dirs, files in os.walk(rootDir):
        files.sort(key=tryint)
        for file in files:
            if "mouth" in file:
                filePath = os.path.join(root, file)
                parentDir = os.path.dirname(root)
                fname = os.path.splitext(os.path.basename(file))[0]
                videoName, frame, facestr = fname.split("_")
                timing = '%.3f' % float(int(frame) / 29.97)
                timing = str(timing).replace('.', '-')
                fileNew = ''.join([videoName, "_", timing, "_mouth.jpg"])  # replace 'face' with 'mouth'
                mouthsDir = ''.join([parentDir, os.sep, "mouthsTiming"])
                if not os.path.exists(mouthsDir):
                    os.makedirs(mouthsDir)
                fileNewPath = ''.join([mouthsDir, os.sep, fileNew])
                print(filePath + "\t -> \t" + fileNewPath)
                # copyfile(filePath, fileNewPath)
                nbCopies += 1
    print(nbCopies, " files have been renamed")
    return 0

    # example usage
    # root = "/home/matthijs/TCDTIMIT/processed2/lipspeakers/Lipspkr1/sa1"
    # frameToTiming(root)