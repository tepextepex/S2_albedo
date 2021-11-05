import os.path
from zipfile import ZipFile
import numpy as np
import matplotlib.pyplot as plt
from osgeo import gdal


def seek_band_path(band_id, zip_path):
    with ZipFile(zip_path, "r") as z:
        for filename in z.namelist():
            if os.path.splitext(filename)[-1] == ".jp2":
                if ("IMG_DATA" in filename) and ("_20m" in filename):
                    if band_id in filename:
                        return filename
                if ("IMG_DATA" in filename) and ("_10m" in filename):
                    if band_id in filename:
                        return filename
        else:
            return None


def seek_and_load(band_id, zip_path):
    path = seek_band_path(band_id, zip_path)
    if path is None:
        print("No needed band!")
    else:
        full_path = "/vsizip/%s/%s" % (zip_path, path)
        res = os.path.splitext(path)[0].split("_")[-1]
        print("Trying to open %s" % full_path)
        ds = gdal.Open(full_path)
        return ds, res


def get_gt_prj(zip_path):
    ds, res = seek_and_load("AOT", zip_path)  # AOT band is always present inside 20m dir
    if ds is None:
        print("Could not open file")
        gt, prj = None, None
    else:
        gt = ds.GetGeoTransform()
        prj = ds.GetProjection()
    return gt, prj


def b(band_id, zip_path):
    ds, res = seek_and_load(band_id, zip_path)
    if ds is None:
        print("Could not open file")
    else:
        print(res)
        if res != "20m":
            ds = gdal.Warp("", ds, format="MEM", xRes=20, yRes=20, srcNodata=None, resampleAlg="bilinear",
                            callback=gdal.TermProgress)
            array = ds.GetRasterBand(1).ReadAsArray()
            # highly likely this is band B08
        else:
            array = ds.GetRasterBand(1).ReadAsArray()
            array = np.where(array == 0, np.nan, array)  # zero is the "fill value" AKA no-value
            # but don't apply this to B08 above - it will be corrupted
        return array


def narrow_to_broad(zip_path, method="liang"):
    """

    :param zip_path:
    :param method: "liang" - Liang (2000); "bonafoni" - Bonafoni & Sekertekin (2020), DOI: 10.1109/LGRS.2020.2967085
    :return:
    """
    z = zip_path
    if method == "bonafoni":
        broad = 0.2266 * b("B02", z) + 0.1236 * b("B03", z) + 0.1573 * b("B04", z) + 0.3417 * b("B08", z) + 0.1170 * b("B11", z) + 0.0338 * b("B12", z)
    if method == "liang":
        broad = 0.356 * b("B02", z) + 0.130 * b("B04", z) + 0.373 * b("B08", z) + 0.085 * b("B11", z) + 0.072 * b("B12", z) - 18
        broad = broad / 10000  # NOTE the mult factor for Sentinel-2 L2A product is now 10000
    # let's truncate the values above 1 and below 0:
    broad = np.where(broad > 1.0, 1.0, broad)
    broad = np.where(broad < 0.0, 0.0, broad)
    return broad


def export_albedo(albedo_array, gt, prj, out_path):
    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(out_path, albedo_array.shape[1], albedo_array.shape[0], 1, gdal.GDT_Float32)
    ds.SetGeoTransform(gt)
    ds.SetProjection(prj)
    ds.GetRasterBand(1).WriteArray(albedo_array)
    ds.FlushCache()
    return out_path


if __name__ == "__main__":
    source_zip = "/home/tepex/AARI/Glaciers/Aldegonda_tc/imagery/s2_orig/S2B_MSIL2A_20210809T115639_N0301_R066_T33XVG_20210809T164242.zip"
    # print(seek_band_path("B03", source_zip))
    # print(seek_band_path("B08", source_zip))
    # print(seek_band_path("unknown-band-id", source_zip))
    gt, prj = get_gt_prj(source_zip)
    albedo = narrow_to_broad(source_zip, method="liang")
    """
    plt.imshow(albedo)
    plt.colorbar()
    plt.show()
    """
    out_path = "%s_albedo.tif" % os.path.splitext(source_zip)[0]
    export_albedo(albedo, gt, prj, out_path)
