"""
HookLibrary seeder — pre-built hook templates per niche.
Run once to populate global hook library.
"""
import uuid
from sqlalchemy.orm import Session
from backend.models.models import HookLibrary

GLOBAL_HOOKS = [
    # motivasi
    ("motivasi", "Kamu gak akan percaya apa yang terjadi kalau kamu lakukan ini setiap hari..."),
    ("motivasi", "Stop buang waktu! Ini yang orang sukses lakukan tiap pagi"),
    ("motivasi", "Kenapa 99% orang gagal? Karena mereka tidak tahu rahasia ini"),
    ("motivasi", "1 kebiasaan kecil yang mengubah hidup saya dalam 30 hari"),
    ("motivasi", "Kalau kamu mau sukses, BERHENTI melakukan hal ini sekarang"),
    ("motivasi", "Orang biasa vs orang luar biasa — bedanya cuma SATU hal"),
    ("motivasi", "Fakta pahit yang tidak ada yang mau ceritain ke kamu"),
    ("motivasi", "Ini alasan kamu belum sukses padahal sudah kerja keras"),
    ("motivasi", "Dalam 60 detik, saya ubah cara pandangmu soal kerja keras"),
    ("motivasi", "Berhenti bilang 'nanti' — masa depanmu dimulai sekarang"),

    # edukasi
    ("edukasi", "Hal yang diajarkan di sekolah tapi SALAH besar"),
    ("edukasi", "Fakta ilmiah yang bikin otak kamu mikir 'kok bisa?'"),
    ("edukasi", "Ternyata selama ini kita salah paham soal ini..."),
    ("edukasi", "Pelajaran penting yang tidak ada di kurikulum sekolah"),
    ("edukasi", "Cara belajar yang benar — bukan yang diajarkan guru"),
    ("edukasi", "Kenapa orang cerdas justru tidak banyak bicara?"),
    ("edukasi", "5 fakta tentang otak yang bikin kamu takjub"),
    ("edukasi", "Apa yang terjadi di otak saat kamu tidur? Ini jawabannya"),
    ("edukasi", "Ilmuwan menemukan sesuatu yang mengubah segalanya"),
    ("edukasi", "Sejarah tersembunyi yang tidak diajarkan di sekolah"),

    # humor
    ("humor", "POV: kamu baru sadar hal ini dan langsung tertawa"),
    ("humor", "Tolong jangan tonton ini kalau kamu gampang ketawa"),
    ("humor", "Ekspektasi vs realita hidup di Indonesia"),
    ("humor", "Hal yang hanya dimengerti orang Indonesia"),
    ("humor", "Ketika bos kamu minta lembur tapi gak ada overtime..."),
    ("humor", "Tanda-tanda kamu sudah tua menurut Gen Z"),
    ("humor", "Tipe-tipe manusia yang pasti kamu temui di kantor"),
    ("humor", "Anak kos pasti relate dengan ini"),
    ("humor", "Weekend plan vs kenyataan"),
    ("humor", "Bahasa tubuh orang Indonesia yang super relatable"),

    # fakta
    ("fakta", "Fakta mengejutkan yang 99% orang tidak tahu"),
    ("fakta", "Ini bukan hoax — fakta yang lebih aneh dari fiksi"),
    ("fakta", "Hal sederhana yang ternyata punya sejarah gelap"),
    ("fakta", "Faktanya... kamu sudah salah paham soal ini"),
    ("fakta", "5 fakta tentang Indonesia yang bikin bangga"),
    ("fakta", "Fakta ilmu pengetahuan yang bikin kepala pusing"),
    ("fakta", "Ini yang terjadi kalau kamu tidak minum air 3 hari"),
    ("fakta", "Misteri alam semesta yang belum terjawab sampai sekarang"),
    ("fakta", "Fakta tentang uang yang tidak diajarkan di sekolah"),
    ("fakta", "Hal-hal yang ternyata lebih berbahaya dari yang kamu kira"),

    # tutorial
    ("tutorial", "Cara yang benar vs cara yang kebanyakan orang lakukan"),
    ("tutorial", "Tutorial 60 detik yang bikin hidupmu lebih mudah"),
    ("tutorial", "Trik simpel yang menghemat 2 jam sehari"),
    ("tutorial", "Stop pakai cara lama! Ini cara yang jauh lebih efektif"),
    ("tutorial", "Langkah-langkah yang seharusnya kamu tahu dari dulu"),
    ("tutorial", "Cara mudah yang tidak pernah diajarkan di mana-mana"),
    ("tutorial", "Ini cara profesional melakukannya — catat baik-baik"),
    ("tutorial", "Kesalahan yang sering dilakukan dan cara memperbaikinya"),
    ("tutorial", "Hack sederhana yang mengubah segalanya"),
    ("tutorial", "Dari nol sampai bisa dalam 1 menit — simak ini"),

    # lifestyle
    ("lifestyle", "Kalau kamu beli ini, kamu rugi besar"),
    ("lifestyle", "Perubahan kecil yang berdampak besar pada hidupmu"),
    ("lifestyle", "Morning routine orang sukses yang bisa kamu tiru"),
    ("lifestyle", "Hal yang harus kamu berhentikan sebelum usia 30"),
    ("lifestyle", "Investasi terbaik yang bisa kamu lakukan hari ini"),
    ("lifestyle", "Kenapa orang kaya tidak tampak kaya?"),
    ("lifestyle", "Kebiasaan buruk yang kamu anggap normal padahal tidak"),
    ("lifestyle", "Cara hidup minimalis yang bikin lebih bahagia"),
    ("lifestyle", "Hal yang harus ada di tasmu setiap hari"),
    ("lifestyle", "Perbandingan: hidup dengan vs tanpa kebiasaan ini"),

    # finance
    ("finance", "Cara orang kaya menyimpan uang yang tidak diajarkan"),
    ("finance", "Kesalahan finansial yang buat kamu miskin terus"),
    ("finance", "Investasi Rp 100 ribu per hari bisa jadi berapa?"),
    ("finance", "Kenapa gaji besar tapi tetap tidak punya tabungan?"),
    ("finance", "Rahasia compound interest yang bikin melongo"),
    ("finance", "Stop beli ini kalau mau kaya"),
    ("finance", "Cara kerja uang yang tidak diajarkan di sekolah"),
    ("finance", "Berapa yang kamu butuhkan untuk pensiun dini?"),
    ("finance", "Strategi saving yang dipakai orang kaya"),
    ("finance", "Perbedaan orang kaya dan miskin dalam mengelola uang"),

    # kesehatan
    ("kesehatan", "Makanan yang kamu anggap sehat ternyata berbahaya"),
    ("kesehatan", "Tanda tubuhmu butuh pertolongan segera"),
    ("kesehatan", "Manfaat tersembunyi dari kebiasaan yang sering diabaikan"),
    ("kesehatan", "Dokter tidak mau ceritain ini ke kamu soal tidur"),
    ("kesehatan", "Olahraga yang paling efektif untuk turun berat badan"),
    ("kesehatan", "Hal yang terjadi di tubuh saat kamu stres"),
    ("kesehatan", "Suplemen yang ternyata tidak perlu kamu beli"),
    ("kesehatan", "Cara alami menurunkan tekanan darah tinggi"),
    ("kesehatan", "Kenapa kamu selalu lelah padahal sudah cukup tidur?"),
    ("kesehatan", "5 tanda tubuhmu dehidrasi yang sering diabaikan"),

    # teknologi
    ("teknologi", "Fitur tersembunyi HP kamu yang tidak banyak tahu"),
    ("teknologi", "AI sudah bisa lakukan ini — masa depan terasa menakutkan"),
    ("teknologi", "Aplikasi gratis yang menggantikan yang bayar ratusan ribu"),
    ("teknologi", "Trik keyboard yang menghemat 1 jam per hari"),
    ("teknologi", "Cara hacker mencuri data kamu tanpa kamu sadari"),
    ("teknologi", "Teknologi yang akan menghilang dalam 5 tahun"),
    ("teknologi", "Setting HP yang harus kamu ubah sekarang"),
    ("teknologi", "Ini yang terjadi kalau AI mengambil alih pekerjaan kamu"),
    ("teknologi", "Cara menggunakan AI untuk produktivitas 10x lipat"),
    ("teknologi", "Tools gratis yang dipakai developer senior setiap hari"),
]


def seed_global_hooks(db: Session) -> int:
    """Seed global hook library. Returns number of hooks added."""
    existing_count = db.query(HookLibrary).filter(
        HookLibrary.tenant_id == None
    ).count()
    if existing_count >= len(GLOBAL_HOOKS):
        return 0

    added = 0
    for niche, hook_text in GLOBAL_HOOKS:
        existing = db.query(HookLibrary).filter(
            HookLibrary.hook_text == hook_text,
            HookLibrary.tenant_id == None,
        ).first()
        if not existing:
            hook = HookLibrary(
                id=str(uuid.uuid4()),
                tenant_id=None,
                niche=niche,
                hook_text=hook_text,
                is_approved=True,
                use_count=0,
            )
            db.add(hook)
            added += 1

    if added:
        db.commit()
    return added
