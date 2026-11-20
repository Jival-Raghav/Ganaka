"""Fixed templates in English / Hindi / Kannada. Amounts are always passed in as already-formatted strings from tool output."""
LANGS = {"en": "English", "hi": "हिन्दी", "kn": "ಕನ್ನಡ"}
BCP = {"en": "en-IN", "hi": "hi-IN", "kn": "kn-IN"}

T = {
 "hello": {"en": "Hello {name}! I'm Ganaka. Ask me about GST, input credit, bills, e-way bills, deadlines or notices — by text or voice.",
           "hi": "नमस्ते {name}! मैं Ganaka हूँ। GST, इनपुट क्रेडिट, बिल, ई-वे बिल, डेडलाइन या नोटिस के बारे में पूछिए।",
           "kn": "ನಮಸ್ಕಾರ {name}! ನಾನು Ganaka. GST, ಇನ್‌ಪುಟ್ ಕ್ರೆಡಿಟ್, ಬಿಲ್, ಇ-ವೇ ಬಿಲ್, ಗಡುವು ಅಥವಾ ನೋಟಿಸ್ ಬಗ್ಗೆ ಕೇಳಿ."},
 "gst_summary": {"en": "For {period}: you sold {sales} and collected {output} in tax. Your input credit cuts this by {itc}. You need to pay {cash} by {due}.",
                 "hi": "{period}: आपकी बिक्री {sales} रही और टैक्स {output} जमा हुआ। इनपुट क्रेडिट {itc} घटाने के बाद आपको {due} तक {cash} देना है।",
                 "kn": "{period}: ನಿಮ್ಮ ಮಾರಾಟ {sales}, ಸಂಗ್ರಹಿಸಿದ ತೆರಿಗೆ {output}. ಇನ್‌ಪುಟ್ ಕ್ರೆಡಿಟ್ {itc} ಕಡಿಮೆ ಮಾಡಿದ ನಂತರ {due} ರೊಳಗೆ {cash} ಪಾವತಿಸಬೇಕು."},
 "itc_stuck": {"en": "{amount} of credit is stuck because suppliers have not filed or the invoices don't match ({suppliers}).",
               "hi": "{amount} का क्रेडिट अटका है क्योंकि सप्लायर ने फाइल नहीं किया या बिल मेल नहीं खाते ({suppliers})।",
               "kn": "{amount} ಕ್ರೆಡಿಟ್ ಸಿಲುಕಿದೆ — ಪೂರೈಕೆದಾರರು ಫೈಲ್ ಮಾಡಿಲ್ಲ ಅಥವಾ ಬಿಲ್ ಹೊಂದಿಕೆಯಾಗುತ್ತಿಲ್ಲ ({suppliers})."},
 "itc_none": {"en": "No input credit is at risk right now.", "hi": "अभी कोई इनपुट क्रेडिट खतरे में नहीं है।", "kn": "ಈಗ ಯಾವುದೇ ಇನ್‌ಪುಟ್ ಕ್ರೆಡಿಟ್ ಅಪಾಯದಲ್ಲಿಲ್ಲ."},
 "bills": {"en": "{n} documents received, {posted} posted to your books, {review} need your help.",
           "hi": "{n} दस्तावेज़ मिले, {posted} बही में दर्ज, {review} में आपकी मदद चाहिए।",
           "kn": "{n} ದಾಖಲೆಗಳು ಬಂದಿವೆ, {posted} ಲೆಡ್ಜರ್‌ಗೆ ಸೇರಿವೆ, {review} ಕ್ಕೆ ನಿಮ್ಮ ಸಹಾಯ ಬೇಕು."},
 "ewb_need": {"en": "{n} dispatch(es) need an e-way bill before the truck leaves. Next: {inv} for {value}.",
              "hi": "{n} डिस्पैच के लिए ट्रक निकलने से पहले ई-वे बिल चाहिए। अगला: {inv}, {value}।",
              "kn": "{n} ರವಾನೆಗೆ ಟ್ರಕ್ ಹೊರಡುವ ಮೊದಲು ಇ-ವೇ ಬಿಲ್ ಬೇಕು. ಮುಂದಿನದು: {inv}, {value}."},
 "ewb_none": {"en": "No dispatch needs an e-way bill right now.", "hi": "अभी किसी डिस्पैच को ई-वे बिल की ज़रूरत नहीं।", "kn": "ಈಗ ಯಾವುದೇ ರವಾನೆಗೆ ಇ-ವೇ ಬಿಲ್ ಬೇಕಿಲ್ಲ."},
 "deadlines": {"en": "Next deadlines: {list}.", "hi": "अगली डेडलाइन: {list}।", "kn": "ಮುಂದಿನ ಗಡುವುಗಳು: {list}."},
 "notices": {"en": "{n} open notice(s). Next reply due {due}.", "hi": "{n} नोटिस खुले हैं। अगला जवाब {due} तक।", "kn": "{n} ನೋಟಿಸ್ ಬಾಕಿ. ಮುಂದಿನ ಉತ್ತರ {due} ರೊಳಗೆ."},
 "no_notices": {"en": "No open notices. {risks} risk warning(s) found in my nightly check.", "hi": "कोई खुला नोटिस नहीं। रात की जाँच में {risks} जोखिम चेतावनी मिली।", "kn": "ಯಾವುದೇ ನೋಟಿಸ್ ಬಾಕಿಯಿಲ್ಲ. ರಾತ್ರಿ ಪರಿಶೀಲನೆಯಲ್ಲಿ {risks} ಅಪಾಯದ ಎಚ್ಚರಿಕೆ."},
 "approvals": {"en": "{n} item(s) are waiting for your approval.", "hi": "{n} चीज़ें आपकी मंज़ूरी का इंतज़ार कर रही हैं।", "kn": "{n} ವಿಷಯಗಳು ನಿಮ್ಮ ಅನುಮೋದನೆಗೆ ಕಾಯುತ್ತಿವೆ."},
 "tds": {"en": "{text}", "hi": "{text}", "kn": "{text}"},
 "suppliers": {"en": "Least reliable supplier: {name} (filed on time {pct}% of invoices).", "hi": "सबसे कम भरोसेमंद सप्लायर: {name} (समय पर {pct}% बिल)।", "kn": "ಕಡಿಮೆ ವಿಶ್ವಾಸಾರ್ಹ ಪೂರೈಕೆದಾರ: {name} (ಸಮಯಕ್ಕೆ {pct}% ಬಿಲ್)."},
 "fallback": {"en": "I can help with: GST this month, input credit, bills received, e-way bills, deadlines, notices, TDS, suppliers. Which one?",
              "hi": "मैं इनमें मदद कर सकता हूँ: इस महीने का GST, इनपुट क्रेडिट, बिल, ई-वे बिल, डेडलाइन, नोटिस, TDS, सप्लायर। कौन सा?",
              "kn": "ನಾನು ಸಹಾಯ ಮಾಡಬಲ್ಲೆ: ಈ ತಿಂಗಳ GST, ಇನ್‌ಪುಟ್ ಕ್ರೆಡಿಟ್, ಬಿಲ್, ಇ-ವೇ ಬಿಲ್, ಗಡುವು, ನೋಟಿಸ್, TDS, ಪೂರೈಕೆದಾರರು. ಯಾವುದು?"},
 "safe_fail": {"en": "I could not verify those numbers against your records, so I won't state them. Please open the proof pack.",
               "hi": "मैं इन आँकड़ों को आपके रिकॉर्ड से सत्यापित नहीं कर सका, इसलिए नहीं बताऊँगा। कृपया प्रूफ पैक खोलें।",
               "kn": "ಈ ಅಂಕಿಗಳನ್ನು ನಿಮ್ಮ ದಾಖಲೆಗಳೊಂದಿಗೆ ಪರಿಶೀಲಿಸಲಾಗಲಿಲ್ಲ; ದಯವಿಟ್ಟು ಪ್ರೂಫ್ ಪ್ಯಾಕ್ ತೆರೆಯಿರಿ."},
 "rule_change": {"en": "Rule update: {title}. From {date}: {what}. {action}", "hi": "नियम में बदलाव: {title}। {date} से: {what}। {action}", "kn": "ನಿಯಮ ಬದಲಾವಣೆ: {title}. {date} ರಿಂದ: {what}. {action}"},
 "ask_confirm": {"en": "Please confirm: {text}", "hi": "कृपया पुष्टि करें: {text}", "kn": "ದಯವಿಟ್ಟು ದೃಢೀಕರಿಸಿ: {text}"},
 # third-party templates (English + local language line)
 "m_supplier_missing_2b": {"en": "This is Ganaka on behalf of {biz} (GSTIN {gstin}). Your invoice {inv} dated {date} for {amount} does not appear in our GSTR-2B. Please upload it in your GSTR-1/IFF. Reply here if you have already filed.",
                           "hi": "नमस्ते। Ganaka, {biz} (GSTIN {gstin}) की ओर से। आपका बिल {inv} दिनांक {date}, {amount}, हमारे GSTR-2B में नहीं दिखता। कृपया GSTR-1/IFF में अपलोड करें। फाइल कर दिया हो तो यहाँ जवाब दें।",
                           "kn": "ನಮಸ್ಕಾರ. Ganaka, {biz} (GSTIN {gstin}) ಪರವಾಗಿ. ನಿಮ್ಮ ಬಿಲ್ {inv} ದಿನಾಂಕ {date}, {amount}, ನಮ್ಮ GSTR-2B ಯಲ್ಲಿ ಕಾಣುತ್ತಿಲ್ಲ. ದಯವಿಟ್ಟು GSTR-1/IFF ನಲ್ಲಿ ಅಪ್‌ಲೋಡ್ ಮಾಡಿ. ಈಗಾಗಲೇ ಫೈಲ್ ಮಾಡಿದ್ದರೆ ಇಲ್ಲಿ ಉತ್ತರಿಸಿ."},
 "m_supplier_mismatch": {"en": "This is Ganaka on behalf of {biz} (GSTIN {gstin}). Invoice {inv} dated {date}: your filing shows {theirs} but our records show {ours}. Please amend in GSTR-1A / check the buyer GSTIN. Reply when done.",
                         "hi": "Ganaka, {biz} (GSTIN {gstin}) की ओर से। बिल {inv} दिनांक {date}: आपकी फाइलिंग में {theirs} है, हमारे रिकॉर्ड में {ours}। कृपया GSTR-1A में सुधार करें।",
                         "kn": "Ganaka, {biz} (GSTIN {gstin}) ಪರವಾಗಿ. ಬಿಲ್ {inv} ದಿನಾಂಕ {date}: ನಿಮ್ಮ ಫೈಲಿಂಗ್‌ನಲ್ಲಿ {theirs}, ನಮ್ಮ ದಾಖಲೆಯಲ್ಲಿ {ours}. ದಯವಿಟ್ಟು GSTR-1A ನಲ್ಲಿ ತಿದ್ದಿ."},
 "m_transporter_partb": {"en": "This is Ganaka for {biz}. Vehicle number for dispatch to {dest} (invoice {inv}, {value})? Reply with the vehicle number, e.g. KA05AB1234.",
                         "hi": "Ganaka, {biz} के लिए। {dest} के डिस्पैच (बिल {inv}, {value}) के लिए गाड़ी नंबर? जैसे KA05AB1234 भेजें।",
                         "kn": "Ganaka, {biz} ಪರವಾಗಿ. {dest} ರವಾನೆ (ಬಿಲ್ {inv}, {value}) ವಾಹನ ಸಂಖ್ಯೆ? ಉದಾ. KA05AB1234."},
 "m_doc_pack": {"en": "Ganaka for {biz}: documents for dispatch to {dest}. Invoice {inv}, e-way bill {ewb} valid until {until}. Vehicle {veh}. Documents attached (simulated). Reply 'vehicle changed to <number>' if the vehicle changes.",
                "hi": "Ganaka, {biz}: {dest} डिस्पैच के दस्तावेज़। बिल {inv}, ई-वे बिल {ewb}, {until} तक वैध। वाहन {veh}। गाड़ी बदलने पर 'vehicle changed to <नंबर>' भेजें।",
                "kn": "Ganaka, {biz}: {dest} ರವಾನೆ ದಾಖಲೆಗಳು. ಬಿಲ್ {inv}, ಇ-ವೇ ಬಿಲ್ {ewb}, {until} ವರೆಗೆ ಮಾನ್ಯ. ವಾಹನ {veh}. ವಾಹನ ಬದಲಾದರೆ 'vehicle changed to <ಸಂಖ್ಯೆ>' ಕಳುಹಿಸಿ."},
 "m_buyer_copy": {"en": "{biz}: invoice {inv} and e-way bill {ewb} for your consignment (valid until {until}). Documents attached (simulated).",
                  "hi": "{biz}: आपकी खेप का बिल {inv} और ई-वे बिल {ewb} ({until} तक वैध)।", "kn": "{biz}: ನಿಮ್ಮ ಸರಕಿನ ಬಿಲ್ {inv} ಮತ್ತು ಇ-ವೇ ಬಿಲ್ {ewb} ({until} ವರೆಗೆ ಮಾನ್ಯ)."},
 "m_ewb_expiry": {"en": "Ganaka for {biz}: e-way bill {ewb} expires {until}. Vehicle {veh}. Reply EXTEND if the consignment needs more time.",
                  "hi": "Ganaka, {biz}: ई-वे बिल {ewb} {until} को समाप्त। और समय चाहिए तो EXTEND लिखें।", "kn": "Ganaka, {biz}: ಇ-ವೇ ಬಿಲ್ {ewb} {until} ಕ್ಕೆ ಮುಗಿಯುತ್ತದೆ. ಹೆಚ್ಚು ಸಮಯ ಬೇಕಿದ್ದರೆ EXTEND ಎಂದು ಕಳುಹಿಸಿ."},
 "m_buyer_overdue": {"en": "{biz} reminder: invoice {inv} for {amount} dated {date} is overdue. Under Section 43B(h) payments to registered micro/small suppliers should be made on time. Please share your payment date.",
                     "hi": "{biz} की ओर से: बिल {inv}, {amount}, दिनांक {date} का भुगतान बकाया है। कृपया भुगतान की तारीख बताएँ।", "kn": "{biz}: ಬಿಲ್ {inv}, {amount}, ದಿನಾಂಕ {date} ಪಾವತಿ ಬಾಕಿ. ಪಾವತಿ ದಿನಾಂಕ ತಿಳಿಸಿ."},
 "m_tds_missing": {"en": "{biz}: TDS of {amount} deducted on invoice {inv} does not appear in our Form 26AS. Please deposit/report it against our PAN and share the challan.",
                   "hi": "{biz}: बिल {inv} पर कटा TDS {amount} हमारे 26AS में नहीं दिख रहा। कृपया जमा/रिपोर्ट करें।", "kn": "{biz}: ಬಿಲ್ {inv} ಮೇಲಿನ TDS {amount} ನಮ್ಮ 26AS ನಲ್ಲಿ ಕಾಣುತ್ತಿಲ್ಲ. ದಯವಿಟ್ಟು ಜಮೆ/ವರದಿ ಮಾಡಿ."},
 "q_amount": {"en": "I couldn't read this clearly. Is the {field} {options}?", "hi": "मैं साफ़ नहीं पढ़ पाया। क्या {field} {options} है?", "kn": "ಇದನ್ನು ಸ್ಪಷ್ಟವಾಗಿ ಓದಲಾಗಲಿಲ್ಲ. {field} {options} ಆಗಿದೆಯೇ?"},
}

WORDS = {"en": {"sales": "sales", "tax": "tax"}, "hi": {}, "kn": {}}


def t(key: str, lang: str = "en", **kw) -> str:
    tpl = T[key].get(lang) or T[key]["en"]
    return tpl.format(**kw)


def detect_lang(text: str, default="en") -> str:
    if any("ಀ" <= c <= "೿" for c in text):
        return "kn"
    if any("ऀ" <= c <= "ॿ" for c in text):
        return "hi"
    low = text.lower()
    if any(w in low for w in ("eshtu", "yaavaga", "enu ", "ee month", "beku", "illa")):
        return "kn"
    if any(w in low for w in ("kitna", "kya ", "mahina", "hai ", "batao")):
        return "hi"
    return default
