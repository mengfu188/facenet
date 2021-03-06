"""Performs face alignment and stores face thumbnails in the output directory."""
# MIT License
# 
# Copyright (c) 2016 David Sandberg
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from scipy import misc
import sys
import os
import argparse
import tensorflow as tf
import numpy as np
import facenet
import align.detect_face
import random
from time import sleep
import matplotlib.pyplot as plt

def main(args):
    sleep(random.random())
    output_dir = os.path.expanduser(args.output_dir)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    # Store some git revision info in a text file in the log directory
    src_path,_ = os.path.split(os.path.realpath(__file__))
    facenet.store_revision_info(src_path, output_dir, ' '.join(sys.argv))
    dataset = facenet.get_dataset(args.input_dir)

    print('Creating networks and loading parameters')

    with tf.Graph().as_default():
        gpu_options = tf.GPUOptions(per_process_gpu_memory_fraction=args.gpu_memory_fraction)
        sess = tf.Session(config=tf.ConfigProto(gpu_options=gpu_options, log_device_placement=False))
        with sess.as_default():
            pnet, rnet, onet = align.detect_face.create_mtcnn(sess, None)

    minsize = 20 # minimum size of face
    threshold = [ 0.6, 0.7, 0.7 ]  # three steps's threshold
    factor = 0.709 # scale factor

    # Add a random key to the filename to allow alignment using multiple processes
    random_key = np.random.randint(0, high=99999)
    bounding_boxes_filename = os.path.join(output_dir, 'bounding_boxes_%05d.txt' % random_key)

    with open(bounding_boxes_filename, "w") as text_file:
        nrof_images_total = 0
        nrof_successfully_aligned = 0
        if args.random_order:
            random.shuffle(dataset)
        for cls in dataset:
            output_class_dir = os.path.join(output_dir, cls.name)
            if not os.path.exists(output_class_dir):
                os.makedirs(output_class_dir)
                if args.random_order:
                    random.shuffle(cls.image_paths)
            for image_path in cls.image_paths:
                nrof_images_total += 1
                filename = os.path.splitext(os.path.split(image_path)[1])[0]
                output_filename = os.path.join(output_class_dir, filename+'.png')
                print(image_path)
                if not os.path.exists(output_filename):
                    try:
                        img = misc.imread(image_path)
                    except (IOError, ValueError, IndexError) as e:
                        errorMessage = '{}: {}'.format(image_path, e)
                        print(errorMessage)
                    else:
                        if img.ndim<2:
                            print('Unable to align "%s"' % image_path)
                            text_file.write('%s\n' % (output_filename))
                            continue
                        if img.ndim == 2:
                            img = facenet.to_rgb(img)
                        img = img[:,:,0:3]

                        bounding_boxes, landmarks = align.detect_face.detect_face(img, minsize, pnet, rnet, onet, threshold, factor)
                        # landmarks shape is (10,n)


                        nrof_faces = bounding_boxes.shape[0]
                        # if nrof_faces==0 and args.save_all:
                        #     scaled = misc.imresize(img, (args.image_size, args.image_size), interp='bilinear')
                        #     misc.imsave(output_filename_n, scaled)

                        if nrof_faces>0:

                            if args.brain:
                                # 改成(n,10)
                                # 左眼为landmark[0],landmark[5]
                                # 有眼为landmark[1],landmark[6]
                                # 鼻子为landmark[2],landmark[7]
                                landmarks = np.transpose(landmarks, (1, 0))
                                # import cv2
                                ocd = os.path.join(output_dir+'_brain', cls.name)
                                get_brain(img, landmarks, args.brain_size, ocd, filename)


                            det = bounding_boxes[:,0:4]
                            det_arr = []
                            img_size = np.asarray(img.shape)[0:2]
                            if nrof_faces>1:
                                if args.detect_multiple_faces:
                                    for i in range(nrof_faces):
                                        det_arr.append(np.squeeze(det[i]))
                                else:
                                    bounding_box_size = (det[:,2]-det[:,0])*(det[:,3]-det[:,1])
                                    img_center = img_size / 2
                                    offsets = np.vstack([ (det[:,0]+det[:,2])/2-img_center[1], (det[:,1]+det[:,3])/2-img_center[0] ])
                                    offset_dist_squared = np.sum(np.power(offsets,2.0),0)
                                    index = np.argmax(bounding_box_size-offset_dist_squared*2.0) # some extra weight on the centering
                                    det_arr.append(det[index,:])
                            else:
                                det_arr.append(np.squeeze(det))

                            for i, det in enumerate(det_arr):
                                det = np.squeeze(det)
                                bb = np.zeros(4, dtype=np.int32)
                                bb[0] = np.maximum(det[0]-args.margin/2, 0)
                                bb[1] = np.maximum(det[1]-args.margin/2, 0)
                                bb[2] = np.minimum(det[2]+args.margin/2, img_size[1])
                                bb[3] = np.minimum(det[3]+args.margin/2, img_size[0])
                                cropped = img[bb[1]:bb[3],bb[0]:bb[2],:]
                                scaled = misc.imresize(cropped, (args.image_size, args.image_size), interp='bilinear')
                                nrof_successfully_aligned += 1
                                filename_base, file_extension = os.path.splitext(output_filename)
                                if args.detect_multiple_faces:
                                    output_filename_n = "{}_{}{}".format(filename_base, i, file_extension)
                                else:
                                    output_filename_n = "{}{}".format(filename_base, file_extension)
                                misc.imsave(output_filename_n, scaled)
                                text_file.write('%s %d %d %d %d\n' % (output_filename_n, bb[0], bb[1], bb[2], bb[3]))
                        else:
                            print('Unable to align "%s"' % image_path)
                            text_file.write('%s\n' % (output_filename))

    print('Total number of images: %d' % nrof_images_total)
    print('Number of successfully aligned images: %d' % nrof_successfully_aligned)


def get_brain(img, landmarks, brain_size,output_class_dir, filename):
    """
    获取脑部地区
    :param image: 图片
    :param landmarks: 五个关键点
    :param output_shape: 保存大小
    :param output_class_dir:  保存路径
    :param filename: 文件名，不带后缀
    :return:
    """
    for landmark in landmarks:
        # cv2.circle(img, (landmark[0],landmark[5]), 1, (255,0,0))
        # cv2.circle(img, (landmark[1], landmark[6]), 1, (255, 0, 0))
        # cv2.circle(img, (landmark[2], landmark[7]), 1, (255, 0, 0))
        # cv2.circle(img, (landmark[3], landmark[8]), 1, (255, 0, 0))
        # cv2.circle(img, (landmark[4], landmark[9]), 1, (255, 0, 0))
        w = (landmark[1] - landmark[0]) * 2
        h = landmark[8] - landmark[5]
        # 左上角坐标，防止超界
        pt1 = (max(int(landmark[0] - w), 0), max(int(landmark[5] - h * 3), 0))
        # 右下角坐标，防止超界
        pt2 = (min(int(landmark[1] + w), img.shape[1]), min(int(landmark[6]), img.shape[0]))
        # cv2.rectangle(img, pt1, pt2, (255, 255, 255), 1)
        # # 裁剪坐标为[y0:y1, x0:x1]
        cropped = img[pt1[1]:pt2[1], pt1[0]:pt2[0]]
        # 如果没有brain_size则按照原本的样子保存
        if brain_size != None:
            scaled = misc.imresize(cropped, (brain_size[0], brain_size[1]), interp='bilinear')
        else:
            scaled = cropped
        if not os.path.exists(output_class_dir):
            os.makedirs(output_class_dir)
        output_brain = os.path.join(output_class_dir, filename + '.png')
        plt.imsave(output_brain, scaled)

def parse_arguments(argv):
    parser = argparse.ArgumentParser()

    parser.add_argument('input_dir', type=str, help='Directory with unaligned images.')
    parser.add_argument('output_dir', type=str, help='Directory with aligned face thumbnails.')
    parser.add_argument('--image_size', type=int,
        help='Image size (height, width) in pixels.', default=182)
    parser.add_argument('--margin', type=int,
        help='Margin for the crop around the bounding box (height, width) in pixels.', default=44)
    parser.add_argument('--random_order',
        help='Shuffles the order of images to enable alignment using multiple processes.', action='store_true')
    parser.add_argument('--gpu_memory_fraction', type=float,
        help='Upper bound on the amount of GPU memory that will be used by the process.', default=0.1)
    parser.add_argument('--detect_multiple_faces', type=bool,
                        help='Detect and align multiple faces per image.', default=False)
    parser.add_argument('--save_all', type=bool, default=False,
                        help='save all image without photo have face', action='store_true')

    # 提取脑部
    parser.add_argument('--brain', action='store_true', default=False,
                        help='提取脑部模式')
    parser.add_argument('--brain_size', type=int, nargs=2,
                        help='要保存的size')
    parser.add_argument('--brain_margin', type=int, default=0,
                        help='脑部区域扩充扩充')
    return parser.parse_args(argv)

if __name__ == '__main__':
    print(parse_arguments(sys.argv[1:]))
    main(parse_arguments(sys.argv[1:]))
