import numpy as np
import pandas as pd
from .image_search import load_image_from_url, encode_image

def build_attraction_image_index(attraction_df, save_path):
    vectors = []
    meta = []

    for idx, row in attraction_df.iterrows():
        img_url = (
            row.get("ThumbnailURL")
            or row.get("Picture.PictureUrl1")
            or row.get("PictureUrl1")
        )
        if not img_url:
            continue

        img = load_image_from_url(img_url)
        if img is None:
            continue

        try:
            vec = encode_image(img)
            vectors.append(vec)
            meta.append({
                "index": idx,
                "AttractionID": row.get("AttractionID"),
                "name": row.get("AttractionName"),
                "image": img_url,
            })
        except:
            continue

    np.save(save_path, {
        "vectors": np.vstack(vectors),
        "meta": meta
    })
