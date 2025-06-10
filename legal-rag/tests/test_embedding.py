import unittest
import numpy as np
import sys
import os


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.embedding import get_embedding

class TestEmbedding(unittest.TestCase):
    
    def test_embedding_creation(self):
        
        text = "This is a test legal document."
        embedding = get_embedding(text)
        
        self.assertIsInstance(embedding, np.ndarray)
        
        self.assertEqual(len(embedding.shape), 1)
        
        self.assertEqual(embedding.shape[0], 384)
        
    def test_embedding_consistency(self):
        
        text = "Legal precedent in contract law."
        
        embedding1 = get_embedding(text)
        embedding2 = get_embedding(text)
        
        np.testing.assert_allclose(embedding1, embedding2, rtol=1e-5)
        
    def test_different_texts_different_embeddings(self):
        text1 = "Contract law governs agreements between parties."
        text2 = "Criminal law deals with offenses against the public."
        
        embedding1 = get_embedding(text1)
        embedding2 = get_embedding(text2)
        
        cosine_sim = np.dot(embedding1, embedding2) / (np.linalg.norm(embedding1) * np.linalg.norm(embedding2))
        self.assertLess(cosine_sim, 0.99)
        
    def test_embedding_normalization(self):
        text = "This is a sample legal text for testing embeddings."
        embedding = get_embedding(text)
        
        #Check that the norm of the embedding is reasonable
        norm = np.linalg.norm(embedding)
        self.assertTrue(0.1 < norm < 100)

if __name__ == "__main__":
    unittest.main()