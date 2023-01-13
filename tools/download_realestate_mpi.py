import multiprocessing
import argparse
import glob
import os
from multiprocessing import Pool, Process
from pytube import YouTube
from time import sleep
from skimage import io
from cv2 import resize as imresize
import numpy as np

'''
multiprocess for data download and process
1. The whole train or test dataset can be divided into N parts, each part can be downloaded and processed by one independent process
2. Inside a process, multiple threads can be spawned to 

'''
class Data:
    def __init__(self, url, seqname, list_timestamps):
        self.url = url
        self.list_seqnames = []
        self.list_list_timestamps = []

        self.list_seqnames.append(seqname)
        self.list_list_timestamps.append(list_timestamps)

    def add(self, seqname, list_timestamps):
        self.list_seqnames.append(seqname)
        self.list_list_timestamps.append(list_timestamps)

    def __len__(self):
        return len(self.list_seqnames)

class Downloader():
    def __init__(self, dataroot, mode, output_root, num_workers = 1) -> None:
        print("[INFO] Loading data list ... ",end='')
        self.dataroot = os.path.join(dataroot, mode)
        self.list_seqnames = sorted(glob.glob(dataroot + '/*.txt'))
        self.output_root = os.path.join(output_root, mode)
        self.mode =  mode
        self.num_workers = num_workers
        if not os.path.exists(self.output_root):
            os.makedirs(self.output_root)
        self.list_data = []
        for txt_file in self.list_seqnames:
                dir_name = txt_file.split('/')[-1]
                seq_name = dir_name.split('.')[0]

                # extract info from txt
                seq_file = open(txt_file, "r")
                lines = seq_file.readlines()
                youtube_url = ""
                list_timestamps= []
                for idx, line in enumerate(lines):
                    if idx == 0:
                        youtube_url = line.strip()
                    else:
                        timestamp = int(line.split(' ')[0])
                        list_timestamps.append(timestamp)
                seq_file.close()

                isRegistered = False
                for i in range(len(self.list_data)):
                    if youtube_url == self.list_data[i].url:
                        isRegistered = True
                        self.list_data[i].add(seq_name, list_timestamps)
                    else:
                        pass

                if not isRegistered:
                    self.list_data.append(Data(youtube_url, seq_name, list_timestamps))

            # self.list_data.reverse()
        print(" Done! ")
        print("[INFO] {} movies are used in {} mode".format(len(self.list_data), self.mode))
    
    def worker(self, data_list):
        curr_proc = multiprocessing.current_process()
        print("[INFO] Start downloading {} movies, current process: {}".format(len(data_list), curr_proc.name))
        for global_count, data in enumerate(data_list):
            print("[INFO] Downloading {}/{}: {} ".format(global_count, len(data_list),  data.url))
            try :
                # sometimes this fails because of known issues of pytube and unknown factors
                yt = YouTube(data.url)
                stream = yt.streams.filter(progressive=True).order_by('resolution').desc().first()

                stream.download(self.output_root,'current_'+self.mode+'_{}'.format(curr_proc.name)+'.tmp')
            except :
                failure_log = open('failed_videos_'+self.mode+'_{}'.format(curr_proc.name)+'.txt', 'a')
                for seqname in data.list_seqnames:
                    failure_log.writelines(seqname + '\n')
                failure_log.close()
                continue

            sleep(1)
            videoname = os.path.join(self.output_root,'current_'+self.mode+'_{}'.format(curr_proc.name)+'.tmp')
            if len(data) == 1: # len(data) is len(data.list_seqnames)
                process(data, 0, videoname, self.output_root)
            else:
                with Pool(processes=self.num_workers) as pool:
                    pool.map(wrap_process, [(data, seq_id, videoname, self.output_root) for seq_id in range(len(data))])
            # remove videos
            command = "rm " + videoname 
            os.system(command)

def wrap_process(list_args):
    return process(*list_args)

def process(data, seq_id, videoname, output_root):
    seqname = data.list_seqnames[seq_id]
    if not os.path.exists(os.path.join(output_root, seqname)):
        os.makedirs(output_root + seqname)

    list_str_timestamps = []
    for timestamp in data.list_list_timestamps[seq_id]:
        timestamp = int(timestamp/1000) 
        str_hour = str(int(timestamp/3600000)).zfill(2)
        str_min = str(int(int(timestamp%3600000)/60000)).zfill(2)
        str_sec = str(int(int(int(timestamp%3600000)%60000)/1000)).zfill(2)
        str_mill = str(int(int(int(timestamp%3600000)%60000)%1000)).zfill(3)
        _str_timestamp = str_hour+":"+str_min+":"+str_sec+"."+str_mill
        list_str_timestamps.append(_str_timestamp)

    # extract frames from a video
    for idx, str_timestamp in enumerate(list_str_timestamps):
        command = 'ffmpeg -ss '+str_timestamp+' -i '+videoname+' -vframes 1 -f image2 '+output_root+seqname+'/'+str(data.list_list_timestamps[seq_id][idx])+'.png'
        # print("current command is {}".format(command))
        os.system(command)

    png_list = glob.glob(output_root+"/"+seqname+"/*.png")

    for pngname in png_list:
        if os.path.exists(pngname):
            print('{} exists'.format(pngname))
            continue
        image = io.imread(pngname)
        if int(image.shape[1]/2) < 500:
            break
        image = imresize(image, (int(image.shape[1]/2), int(image.shape[0]/2)))
        io.imsave(pngname, image)


parser = argparse.ArgumentParser()
parser.add_argument('--cameras_dir', default='/home/xxy/Documents/data/RealEstate10K', type=str)
parser.add_argument('--videos_dir', default='/home/xxy/Documents/data/RealEstate10K/videos', type=str)
parser.add_argument('--mode', default='train', type=str)
parser.add_argument('--ntasks', default=8, type=int)
parser.add_argument('--cpus_per_task', default=8, type=int)
parser.add_argument('--parallel', default=False, action='store_true')
args = parser.parse_args()

if __name__=='__main__':
    D = Downloader(dataroot=args.cameras_dir, mode=args.mode, output_root = args.videos_dir, num_workers=args.cpus_per_task)
    list_data = D.list_data 
    NTASKS = args.ntasks
    split_data_list = np.array_split(np.array(list_data), NTASKS)
    for n in range(NTASKS):
        proc = Process(target = D.worker, args = (split_data_list[n],))
        proc.start()
        proc.join()