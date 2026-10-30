"""
Khmer Linguistic Sanitizer & Phonetic Enhancer
=============================================
Provides clean Khmer text for AI generation, Edge-TTS speech synthesis, and video subtitles:
1. Strips foreign scripts (Thai / Chinese leakage from LLMs like 'ยอม' -> 'ព្រម').
2. Replaces mispronounced words: 'មតិ' -> 'ការយល់ឃើញ'.
3. Expands Khmer duplication symbol 'ៗ' into full spoken repeated words ('ថ្មី ថ្មី', 'ច្រើន ច្រើន').
4. Ensures question sentences end with '?' for rising interrogative pitch in Edge-TTS.
"""

import re

# Comprehensive dictionary of Khmer words commonly used with duplication symbol 'ៗ'
COMMON_DUPLICATED_WORDS = [
    'ថ្មី', 'ប្លែក', 'ច្រើន', 'ញឹកញាប់', 'ផ្សេង', 'ដដែល', 'មួយ', 'ឆ្ងាញ់',
    'ក្មេង', 'តិច', 'យឺត', 'លឿន', 'ពិត', 'ច្បាស់', 'សប្បាយ', 'គ្រប់',
    'ជិត', 'ឆ្ងាយ', 'ខ្លាំង', 'ខុស', 'ដូច', 'ឆាប់', 'មុន', 'ក្រោយ',
    'លើ', 'ក្រោម', 'ល្អ', 'អាក្រក់', 'ធំ', 'តូច', 'វែង', 'ខ្លី',
    'ងាយ', 'ស្រួល', 'លំបាក', 'ពិបាក', 'ចាស់', 'ដើម', 'ចុង', 'រាល់',
    'រឿយ', 'កម្រ', 'ត្រង់', 'វៀច', 'ស្អាត', 'រហ័ស', 'រឹង', 'ទន់',
    'ផ្អែម', 'ជូរ', 'ហឹរ', 'ប្រៃ', 'ក្តៅ', 'ត្រជាក់', 'ក្រ', 'មាន',
    'ឆ្លាត', 'ល្ងង់', 'ស្ងាត់', 'ឮ', 'ក្រាស់', 'ស្តើង', 'ទទេ', 'ពេញ',
    'ស្រដៀង', 'តិចតួច', 'បន្តិចបន្តួច', 'ញឹក'
]

# Common Thai words that occasionally bleed from multilingual LLM outputs
THAI_TO_KHMER_MAP = {
    'ยอม': 'ព្រម',
    'และ': 'និង',
    'หรือ': 'ឬ',
    'ที่': 'ដែល',
    'មិន': 'មិន',
    'បាន': 'បាន'
}

# Khmer question words that require a rising tone with '?'
QUESTION_INDICATORS = [
    r'តើ',
    r'ហេតុអ្វី',
    r'យ៉ាងដូចម្តេច',
    r'យ៉ាងម៉េច',
    r'ដែរឬទេ',
    r'ដែរទេ',
    r'ដែរឬអត់',
    r'មែនទេ',
    r'មែនអត់',
    r'មែនឬ',
    r'នរណា',
    r'ឯណា',
    r'ទីណា',
    r'កន្លែងណា',
    r'ពេលណា',
    r'ប៉ុន្មាន',
    r'យ៉ាងណា'
]

Q_REGEX = re.compile('|'.join(QUESTION_INDICATORS))

def clean_foreign_scripts(text: str) -> str:
    """លុបបំបាត់អក្សរថៃ និងចិនចេញពីអត្ថបទខ្មែរ ដោយប្តូរពាក្យដែលជួបញឹកញាប់ជាភាសាខ្មែរ"""
    if not text:
        return ""
    
    # ប្តូរពាក្យថៃដែលជ្រាបចូលមក (Leakage) ជាភាសាខ្មែរ
    for th, km in THAI_TO_KHMER_MAP.items():
        text = text.replace(th, km)
        
    # លុបអក្សរថៃដែលនៅសល់ទាំងអស់ (Thai Unicode Block: U+0E00 - U+0E7F)
    text = re.sub(r'[\u0E00-\u0E7F]+', '', text)
    
    # លុបអក្សរចិន (Chinese / CJK Ideographs: U+4E00 - U+9FFF)
    text = re.sub(r'[\u4E00-\u9FFF]+', '', text)
    
    return text

def replace_mati_word(text: str) -> str:
    """ជំនួសពាក្យ 'មតិ' ដោយ 'ការយល់ឃើញ' ដើម្បីឱ្យសំឡេងអាន AI បញ្ចេញសម្លេងបានត្រឹមត្រូវ"""
    if not text:
        return ""
    text = re.sub(r'មតិយោបល់', 'ការយល់ឃើញ', text)
    text = re.sub(r'មតិ', 'ការយល់ឃើញ', text)
    return text

def expand_khmer_repetition(text: str) -> str:
    """ពង្រីកសញ្ញាផ្ទួន (ៗ) ទៅជាពាក្យពេញចំនួន ២ ដង ដើម្បីឱ្យ Edge-TTS អានផ្ទួនបានត្រឹមត្រូវ"""
    if not text or 'ៗ' not in text:
        return text
        
    # ១. ជំនួសពាក្យពេញនិយមក្នុងបញ្ជី (Known common words)
    for w in sorted(COMMON_DUPLICATED_WORDS, key=len, reverse=True):
        text = re.sub(rf'{w}\s*ៗ', f'{w} {w}', text)
        
    # ២. ជំនួសពាក្យខ្មែរដែលមាន space នៅខាងមុខ
    text = re.sub(r'(\s[\u1780-\u17D3\u17D9-\u17DD]{1,15})\s*ៗ', r'\1 \1', text)
    
    # ៣. ដកសញ្ញា ៗ ដែលនៅសល់ចោល
    text = text.replace('ៗ', '')
    return text

def fix_question_intonation(text: str) -> str:
    """ធានាថាល្បះសំណួរ ឬល្បះចោទសួរទាំងអស់ ត្រូវបញ្ចប់ដោយសញ្ញាសួរ (?) សម្រាប់សំឡេងអាន"""
    if not text:
        return ""
        
    lines = text.split('\n')
    fixed_lines = []
    
    for line in lines:
        if not line.strip():
            fixed_lines.append(line)
            continue
            
        # បំបែកតាមសញ្ញាបញ្ចប់ល្បះ
        parts = re.split(r'([។?!])', line)
        reconstructed = []
        i = 0
        while i < len(parts):
            seg = parts[i]
            punct = parts[i+1] if i + 1 < len(parts) else ''
            i += 2
            
            # ប្រសិនបើក្នុងឃ្លាមានពាក្យចោទសួរ
            if Q_REGEX.search(seg):
                # ប្រសិនបើបញ្ចប់ដោយ ។ ឬគ្មានសញ្ញា ត្រូវប្តូរជា ?
                if punct == '។' or not punct:
                    punct = '?'
            reconstructed.append(seg + punct)
            
        fixed_lines.append(''.join(reconstructed))
        
    return '\n'.join(fixed_lines)

def sanitize_khmer_script(text: str) -> str:
    """
    អនុវត្តដំណើរការកែសម្រួលភាសាខ្មែរទាំង ៤ ដំណាក់កាលពេញលេញ៖
    ១. លុបអក្សរថៃ/ចិន (Clean Foreign Scripts)
    ២. ជំនួស 'មតិ' ➔ 'ការយល់ឃើញ'
    ៣. ពង្រីកសញ្ញា 'ៗ' ➔ ពាក្យផ្ទួន ២ ដង (Expand Repetition)
    ៤. បន្ថែមសញ្ញាសួរ '?' លើល្បះចោទសួរ (Fix Question Intonation)
    """
    if not text:
        return ""
        
    text = clean_foreign_scripts(text)
    text = replace_mati_word(text)
    text = expand_khmer_repetition(text)
    text = fix_question_intonation(text)
    
    return text

