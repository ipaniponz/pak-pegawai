-- Label & persentase predikat kinerja (lihat 1.5s brief). Editable lewat
-- /pengaturan/predikat-kinerja -- ini hanya seed awal sesuai aturan
-- Permendikdasmen yang berlaku saat brief ditulis.

INSERT INTO predikat_referensi (nama, persentase, urutan) VALUES
('Sangat Baik', 1.50, 1),
('Baik', 1.00, 2),
('Butuh Perbaikan', 0.75, 3),
('Kurang', 0.50, 4),
('Sangat Kurang', 0.25, 5);
