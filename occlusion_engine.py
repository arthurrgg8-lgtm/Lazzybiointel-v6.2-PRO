import cv2
import numpy as np
from insightface.app import FaceAnalysis

class OcclusionEngine:
    """
    Extra engine focusing on upper face for disguise / mask cases.
    Does not change UltimateVerifier.
    """

    def __init__(self, providers=None):
        print("OcclusionEngine initialized") 
        if providers is None:
            providers = ["CPUExecutionProvider"]

        # Start with same model; you can later swap to a more occlusion‑robust one.
        self.app = FaceAnalysis(name="buffalo_l", providers=providers)
        self.app.prepare(ctx_id=0, det_size=(640, 640))

    def embed_upper_face(self, path: str):
        img = cv2.imread(path)
        if img is None:
            return None

        h, w = img.shape[:2]

        # Focus on upper 60% (eyes + forehead, less beard/mask area)
        y0, y1 = 0, int(0.6 * h)
        upper = img[y0:y1, :]

        faces = self.app.get(upper)
        if not faces:
            return None
        return faces[0].embedding


def cosine_sim(a, b) -> float:
    if a is None or b is None:
        return 0.0
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))
