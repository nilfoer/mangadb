// window will get redrawn every time its opened so we cant store values there
// browser.tabs.query({active:true,currentWindow:true}).then(function(tabs){
//     //'tabs' will be an array with only one element: an Object describing the active tab
//     //  in the current window.
//     // this == moz-extension window popup
//     currentTabUrl = tabs[0].url;
//     var current_url = document.getElementById("Title").innerHTML;
//     console.log("TAB:"+currentTabUrl+";;"+"CURR:"+current_url);
//     if (current_url != currentTabUrl) {
//         browser.tabs.executeScript({
//           file: "tsu_book.js"
//         });
//     }
// });
browser.tabs.executeScript({
  file: "tsu_book.js"
});

function fillInBookInfo(req, sender, sendResponse) {
    if (req.action == "show_book_info") {
        // document.getElementById("current-url").attributes.content.value = req.url;
        console.log(req.action);
        book_info = req.book_info;
        ei_info = req.ei_info;
        // would need to check utility func to check if obj empty
        // so just check for title
        if (book_info.Title) {
            document.getElementById("cover").style.backgroundImage = "url('" + req.cover_url + "')";
            document.getElementById("Title").innerText = book_info.Title;
            document.getElementById("List").innerText = book_info.List;
            document.getElementById("LastChange").innerText = book_info.LastChange;
            document.getElementById("goto-book-link").href = book_info.WebGUIUrl;
            if (ei_info.LastUpdate) {
                document.getElementById("Uploader").innerText = ei_info.Uploader;
                document.getElementById("UploadDate").innerText = ei_info.UploadDate;
                document.getElementById("Censorship").innerText = ei_info.Censorship;
                document.getElementById("Downloaded").innerText = ei_info.Downloaded;
                document.getElementById("LastUpdate").innerText = ei_info.LastUpdate;
                document.getElementById("toggle-dl").dataset.eiId = ei_info.ExtInfoId;
                if (ei_info.MultipleEi) {
                    document.getElementById("multiple-ei-warning").style.display = "flex";
                }
            } else {
                document.getElementById("ext-info-data-container").style.display = "none";
                document.getElementById("error").style.display = "flex";
                document.getElementById("error").innerText = "No matching external info!";
            }
        } else {
            document.getElementById("book-info-data-container").style.display = "none";
            document.getElementById("ext-info-data-container").style.display = "none";
        }
    } else if (req.action == "toggle_dl") {
        document.getElementById("Downloaded").innerText = req.Downloaded;
    }

}
browser.runtime.onMessage.addListener(fillInBookInfo);

function toggleDl(element) {
    // + to convert to int
    let ei_id = +this.dataset.eiId;
    let before = document.getElementById("Downloaded").innerText;
    browser.runtime.sendMessage({
        action: "toggle_dl",
        ei_id: ei_id,
        before: before
    });
}
document.getElementById("toggle-dl").addEventListener("click", toggleDl);
