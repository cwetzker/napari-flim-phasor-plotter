from magicgui import magic_factory, magicgui
from napari.utils import progress
from time import sleep
import random

from magicgui.tqdm import tqdm, trange

# if magicui.tqdm.tqdm or trange are used outside of a @magicgui function, (such as in
# interactive use in IPython), then they fall back to the standard terminal output

# If use inside of a magicgui-decorated function
# a progress bar widget will be added to the magicgui container


# @magic_factory(call_button='Convert', layout="vertical")
# def convert_folder_to_zarr(steps=10, delay=0.1):
#     import numpy as np
#     """Long running computation with range iterator."""
#     # trange(steps) is a shortcut for `tqdm(range(steps))`
#     A = np.arange(steps).tolist()
#     B = [A]
#     for _i, _v in zip(range(len(B)), tqdm(B, label='time_points')):
#         for _j, _w in zip(range(len(A)), tqdm(A, label='z-slices')):
#             sleep(delay)


@magic_factory(call_button='Convert', layout="vertical",
               cancel_button={'widget_type': 'PushButton',
                              'visible': False,
                              'text': 'Cancel', })
def convert_folder_to_zarr(folder_path: str, cancel_button: bool = False):
    """ Convert a folder of FLIM images to a zarr file.

    The folder must contain only FLIM images of the same type (e.g. all .ptu files or all .sdt files).
    The file names must be in the format: "name_t000_z000" where "t000" is the time point and "z000" is the z slice.
The z slice and time point must be the last two numbers in the file
name. The z slice and time point must be separated by an underscore.

    Parameters
    ----------
    folder_path : str
        Path to the folder containing the FLIM images.
    """
    import zarr
    import dask.array as da
    from pathlib import Path
    from natsort import natsorted
    from napari_flim_phasor_calculator._reader import read_single_ptu_file, read_single_sdt_file, read_single_tif_file
    from napari_flim_phasor_calculator._reader import get_read_function_from_extension, get_most_frequent_file_extension
    from napari_flim_phasor_calculator._reader import get_max_slice_shape_and_dtype, get_structured_list_of_paths
    from napari_flim_phasor_calculator._reader import get_max_zslices, get_max_time_points

    folder_path = Path(folder_path)
    file_extension = get_most_frequent_file_extension(folder_path)
    # Get appropriate read function from file extension
    imread = get_read_function_from_extension[file_extension]
    # Get all file path with specified file extension
    file_paths = natsorted([file_path for file_path in folder_path.iterdir() if file_path.suffix == file_extension])
    # Get maximum shape and dtype from file names (file names must be in the format: "name_t000_z000")
    image_slice_shape, image_dtype = get_max_slice_shape_and_dtype(file_paths, file_extension)
    # Get maximum time and z from file names
    max_z = get_max_zslices(file_paths, file_extension)
    max_time_point = get_max_time_points(file_paths, file_extension)
    # Build stack shape with the fllowing convention: (channel, ut, time, z, y, x)
    stack_shape = (*image_slice_shape[:-2], max_time_point, max_z, *image_slice_shape[-2:])
    # Get a nested list of time point containing a list of z slices
    list_of_time_point_paths = get_structured_list_of_paths(file_paths, file_extension)
    # zarr file will be saved in the same folder as the input folder
    output_path = folder_path / (folder_path.stem + '.zarr')
    # Using zarr to automatically guess chunk sizes
    # Create an empty zarr array of a specified shape and dtype filled with zeros
    zarr_array = zarr.open(output_path, mode='w', shape=stack_shape, dtype=image_dtype)
    # Using dask to rechunk micro-time axis in single chunk (for fft calculation afterwards)
    dask_array = da.from_zarr(output_path)
    # Rechunk axis 1 (micro-time axis) to a single chunk
    dask_array = dask_array.rechunk(chunks={1: -1})
    # Overwriting previous zarr rechunked
    da.to_zarr(dask_array, output_path, overwrite=True)
    # Read zarr as read/write
    zarr_array = zarr.open(output_path, mode='r+')
    # Fill zarr array with data
    for z_paths, i in zip(tqdm(list_of_time_point_paths, label='time_points'), range(len(list_of_time_point_paths))):
        for path, j in zip(tqdm(z_paths, label='z-slices'), range(len(z_paths))):
            data, _ = imread(path)
            zarr_array[:data.shape[0], :data.shape[1], i, j, :data.shape[2], :data.shape[3]] = data

    print('Done')
