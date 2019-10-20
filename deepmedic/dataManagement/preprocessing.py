# Copyright (c) 2016, Konstantinos Kamnitsas
# All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the BSD license. See the accompanying LICENSE file
# or read the terms at https://opensource.org/licenses/BSD-3-Clause.

from __future__ import absolute_import, division

import numpy as np
    

def calc_border_int_of_3d_img(img_3d):
    border_int = np.mean([img_3d[0, 0, 0],
                          img_3d[-1, 0, 0],
                          img_3d[0, -1, 0],
                          img_3d[-1, -1, 0],
                          img_3d[0, 0, -1],
                          img_3d[-1, 0, -1],
                          img_3d[0, -1, -1],
                          img_3d[-1, -1, -1]
                          ])
    return border_int

# ============= Padding =======================

def calc_pad_per_axis(pad_input_imgs, dims_img, dims_rec_field, dims_highres_segment):
    # dims_rec_field: size of CNN's receptive field. [x,y,z]
    # dims_highres_segment: The size of image segments that the cnn gets.
    #     So that we calculate the pad that will go to the side of the volume.
    if not pad_input_imgs:
        return ((0, 0), (0, 0), (0, 0))
    
    rec_field_array = np.asarray(dims_rec_field, dtype="int16")
    dims_img_arr = np.asarray(dims_img,dtype="int16")
    dims_segm_arr = np.asarray(dims_highres_segment, dtype="int16")
    # paddingValue = (img[0, 0, 0] + img[-1, 0, 0] + img[0, -1, 0] + img[-1, -1, 0] + img[0, 0, -1]
    #                 + img[-1, 0, -1] + img[0, -1, -1] + img[-1, -1, -1]) / 8.0
    # Calculate how much padding needed to fully infer the original img, taking only the receptive field in account.
    pad_left = (rec_field_array - 1) // 2
    pad_right = rec_field_array - 1 - pad_left
    # Now, to cover the case that the specified size for sampled image-segment is larger than the image
    # (eg full-image inference and current image is smaller), pad further to right.
    extra_pad_right = np.maximum(0, dims_segm_arr - (dims_img_arr + pad_left + pad_right))
    pad_right += extra_pad_right
    
    pad_left_right_per_axis = ((pad_left[0], pad_right[0]),
                               (pad_left[1], pad_right[1]),
                               (pad_left[2], pad_right[2]))
    
    return pad_left_right_per_axis

# The padding / unpadding could probably be done more generically.
# These pad/unpad should have their own class, and an instance should be created per subject.
# So that unpad gets how much to unpad from the pad.
def pad_imgs_of_case(channels, gt_lbl_img, roi_mask, wmaps_to_sample_per_cat,
                     pad_input_imgs, dims_rec_field, dims_highres_segment):
    # channels: np.array of dimensions [n_channels, x-dim, y-dim, z-dim]
    # gt_lbl_img: np.array
    # roi_mask: np.array
    # wmaps_to_sample_per_cat: np.array of dimensions [num_categories, x-dim, y-dim, z-dim]
    # dims_highres_segment: list [x,y,z] of dimensions of the normal-resolution samples for cnn.
    # Returns:
    # pad_left_right_axes: Padding added before and after each axis. All 0s if no padding.
    
    # Padding added before and after each axis. ((0, 0), (0, 0), (0, 0)) if no pad.
    pad_left_right_per_axis = calc_pad_per_axis(pad_input_imgs,
                                                channels[0].shape, dims_rec_field, dims_highres_segment)
    if not pad_input_imgs:
        return channels, gt_lbl_img, roi_mask, wmaps_to_sample_per_cat, pad_left_right_axes
    
    channels = pad_4d_arr(channels, pad_left_right_per_axis)

    if gt_lbl_img is not None:
        gt_lbl_img = pad_3d_img(gt_lbl_img, pad_left_right_per_axis)
    
    if roi_mask is not None:
        roi_mask = pad_3d_img(roi_mask, pad_left_right_per_axis)
    
    if wmaps_to_sample_per_cat is not None:
        wmaps_to_sample_per_cat = pad_4d_arr(wmaps_to_sample_per_cat, pad_left_right_per_axis)
    
    return channels, gt_lbl_img, roi_mask, wmaps_to_sample_per_cat, pad_left_right_per_axis

def pad_4d_arr(arr_4d, pad_left_right_per_axis_3d):
    # Do not pad first dimension. E.g. for channels or weightmaps, [n_chans,x,y,z]
    pad_left_right_per_axis_4d = ((0,0),) + pad_left_right_per_axis_3d
    return np.lib.pad(arr_4d, pad_left_right_per_axis_4d, 'reflect')

def pad_3d_img(img, pad_left_right_per_axis):
    # img: 3D array.
    # pad_left_right_per_axis is returned in order for unpadding to know how much to remove.
    return np.lib.pad(img, pad_left_right_per_axis, 'reflect')

# In the 3 first axes. Which means it can take a 4-dim image.
def unpad_3d_img(img, padding_left_right_per_axis):
    # img: 3d array
    # padding_left_right_per_axis : ((pad-left-x,pad-right-x), (pad-left-y,pad-right-y), (pad-left-z,pad-right-z))
    unpadded_img = img[padding_left_right_per_axis[0][0]:,
                       padding_left_right_per_axis[1][0]:,
                       padding_left_right_per_axis[2][0]:]
    # The checks below are to make it work if padding == 0, which may happen for 2D on the 3rd axis.
    unpadded_img = unpadded_img[:-padding_left_right_per_axis[0][1], :, :] \
        if padding_left_right_per_axis[0][1] > 0 else unpadded_img
    unpadded_img = unpadded_img[:, :-padding_left_right_per_axis[1][1], :] \
        if padding_left_right_per_axis[1][1] > 0 else unpadded_img
    unpadded_img = unpadded_img[:, :, :-padding_left_right_per_axis[2][1]] \
        if padding_left_right_per_axis[2][1] > 0 else unpadded_img
        
    return unpadded_img


# ============================ (below) Intensity Normalization. ==================================
# Could make classes? class Normalizer and children? (zscore)

# Main normalization method. This calls each different type of normalizer.
def normalize_int_of_imgs(log, channels, roi_mask, prms, job_id):
    if prms is not None:
        channels = normalize_int_zscore(log, channels, roi_mask, prms['zscore'], job_id)
    return channels


# ===== (below) Z-Score Intensity Normalization. =====

def get_img_stats(img):
    return np.mean(img), np.std(img), np.max(img)


def get_cutoff_mask(img, low, high):
    low_mask = img > low
    high_mask = img < high
    return low_mask * high_mask


def get_norm_stats(log, img, roi_mask_bool,
                   cutoff_percents, cutoff_times_std, cutoff_below_mean,
                   verbose=False, job_id=''):

    img_mean, img_std, img_max = get_img_stats(img)

    img_roi = img[roi_mask_bool]  # This gets flattened automatically. It's a vector array.
    img_roi_mean, img_roi_std, img_roi_max = get_img_stats(img_roi)

    # Init auxiliary variables
    mask_bool_norm = roi_mask_bool.copy()
    if cutoff_percents is not None:
        cutoff_low = np.percentile(img_roi, cutoff_percents[0])
        cutoff_high = np.percentile(img_roi, cutoff_percents[1])
        mask_bool_norm *= get_cutoff_mask(img, cutoff_low, cutoff_high)
        if verbose:
            log.print3(job_id + " Cutting off intensities with [percentiles] (within ROI)."
                                " Cutoffs: Min=" + str(cutoff_low) + ", High=" + str(cutoff_high))

    if cutoff_times_std is not None:
        cutoff_low = img_roi_mean - cutoff_times_std[0] * img_roi_std
        cutoff_high = img_roi_mean + cutoff_times_std[1] * img_roi_std
        mask_bool_norm *= get_cutoff_mask(img, cutoff_low, cutoff_high)
        if verbose:
            log.print3(job_id + " Cutting off intensities with [std] (within ROI)."
                                " Cutoffs: Min=" + str(cutoff_low) + ", High=" + str(cutoff_high))

    if cutoff_below_mean:
        cutoff_low = img_mean
        mask_bool_norm *= get_cutoff_mask(img, cutoff_low, img_max)  # no high cutoff
        if verbose:
            log.print3(job_id + " Cutting off intensities [below original img mean] (to cut air)."
                                " Cutoff: Min=" + str(cutoff_low))

    norm_mean, norm_std, _ = get_img_stats(img[mask_bool_norm])

    return norm_mean, norm_std

# Unused
def print_norm_log(log, prms, n_channels, job_id=''):
    # Not useful, because a bug can lead to this to being printed without cutoffs used in practice.
    # Example of such a bug: if these checks and those in the main function become different.
    cutoff_types = []

    if prms['cutoff_percents'] is not None:
        cutoff_types += ['Percentile']
    if prms['cutoff_times_std'] is not None:
        cutoff_types += ['Standard Deviation']
    if prms['cutoff_below_mean']:
        cutoff_types += ['Whole Image Mean']

    log.print3(job_id + " Normalizing " + str(n_channels) + " channel(s) with the following cutoff type(s): " +
               ', '.join(list(cutoff_types)) if cutoff_types else 'None')

# Main z-score method.
def normalize_int_zscore(log, channels, roi_mask, prms, job_id=''):
    # channels: array [n_channels, x, y, z]
    # roi_mask: array [x,y,z]
    # norm_params: {'apply': a, 'cutoff_percents': b, 'cutoff_times_std': c, 'cutoff_below_mean': d}
    #     apply            : Whether to perform z-score normalization. True / False
    #     cutoff_percents  : percentile cutoff (floats: [low_percentile, high_percentile], values in [0-100])
    #     cutoff_times_std : cutoff in terms of standard deviation (floats: [low_multiple, high_multiple])
    #     cutoff_below_mean: low cutoff of whole image mean (True or False)
    # For BRATS: cutoff_perc: [5., 95], cutoff_times_std: [2., 2.], cutoff_below_mean: True
    # job_id: string for logging, specifying job number and pid. In testing, "".
    
    if prms is None or not prms['apply']:
        return channels
    
    channels_norm = np.zeros(channels.shape)
    roi_mask_bool = roi_mask > 0
    verbose = prms['verbose']
    
    for idx, channel in enumerate(channels):
        norm_mean, norm_std = get_norm_stats(log, channel, roi_mask_bool,
                                             prms['cutoff_percents'],
                                             prms['cutoff_times_std'],
                                             prms['cutoff_below_mean'],
                                             verbose,
                                             job_id)
        # Apply the normalization
        channels_norm[idx] = (channel - norm_mean) / (1.0 * norm_std)

        if verbose:
            old_mean, old_std, _ = get_img_stats(channel)
            log.print3(job_id + " Original image stats (channel " + str(idx) + "):" +
                       " Mean=" + str(old_mean) + ", Std=" + str(old_std))
            log.print3(job_id + " Image was normalized using: Mean=" + str(norm_mean) + ", Std=" + str(norm_std))
            new_mean, new_std, _ = get_img_stats(channels_norm[idx])
            log.print3(job_id + " Normalized image stats (channel " + str(idx) + "):" +
                       " Mean=" + str(new_mean) + ", Std=" + str(new_std))

    return channels_norm

# ====================== (above) Z-Score Intensity Normalization. ==================

# ================= Others ========================
# Deprecated
def reflect_array_if_needed(reflect_flags, arr):
    strides_for_refl_per_dim = [-1 if reflect_flags[0] else 1,
                              -1 if reflect_flags[1] else 1,
                              -1 if reflect_flags[2] else 1]
    
    refl_arr = arr[::strides_for_refl_per_dim[0],
                   ::strides_for_refl_per_dim[1],
                   ::strides_for_refl_per_dim[2]]
    return refl_arr

