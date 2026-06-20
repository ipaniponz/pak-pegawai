-- Data master koefisien & ambang AK per jenjang (Pasal 37 PermenPANRB 1/2023).
-- ak_kumulatif_minimal sudah sesuai AGENT_BRIEF 1.1.
-- ak_pangkat_minimal diambil dari tabel "MATRIKS PEGANGAN ANGKA KREDIT KETERAMPILAN
-- DAN KEAHLIAN" di sheet "Monitoring AK" milik Biro Hukum (sumber yang sama dipakai
-- brief 1.4f) -- termasuk Pemula yang tidak disebut brief 1.4f tapi ada di matriks
-- sumber. Bisa diedit lewat /pengaturan/jenjang-referensi (lihat 1.5r) kalau regulasi
-- berubah, jadi nilai di sini hanya seed awal.

INSERT INTO jenjang_referensi (kategori, nama_jenjang, golru, koefisien_ak_tahun, ak_kumulatif_minimal, ak_pangkat_minimal, urutan) VALUES
('Keahlian', 'Ahli Pertama', 'III/a, III/b', 12.5, 100, 50, 1),
('Keahlian', 'Ahli Muda',    'III/c, III/d', 25,   200, 100, 2),
('Keahlian', 'Ahli Madya',   'IV/a, IV/b, IV/c', 37.5, 450, 150, 3),
('Keahlian', 'Ahli Utama',   'IV/d, IV/e', 50,   NULL, 200, 4),
('Keterampilan', 'Pemula',    'II/a', 3.75, 15,  15, 1),
('Keterampilan', 'Terampil',  'II/b, II/c, II/d', 5,  40, 20, 2),
('Keterampilan', 'Mahir',     'III/a, III/b', 12.5, 100, 50, 3),
('Keterampilan', 'Penyelia',  'III/c, III/d', 25,  NULL, 100, 4);
