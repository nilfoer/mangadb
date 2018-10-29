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
        let book_info = req.book_info;
        let ei_info = req.ei_info;
        // would need to check utility func to check if obj empty
        // so just check for title
        if (book_info.Title) {
            document.getElementById("cover").style.backgroundImage = "url('" + req.cover_url + "')";
            document.getElementById("Title").innerText = book_info.Title;
            document.getElementById("List").value = book_info.List;
            document.getElementById("List").dataset.before = book_info.List;
            document.getElementById("List").dataset.book_id = book_info.BookID;
            document.getElementById("LastChange").innerText = book_info.LastChange;
            document.getElementById("goto-book-link").href = book_info.WebGUIUrl;
            document.getElementById("Favorite").innerText = book_info.Favorite;
            document.getElementById("toggle-fav").dataset.book_id = book_info.BookID;
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
    } else if (req.action == "toggle_fav") {
        document.getElementById("Favorite").innerText = req.Favorite;
    } else if (req.action == "set_lists") {
        document.getElementById("List").value = req.List;
        document.getElementById("List").dataset.before = req.List;
    }

}
browser.runtime.onMessage.addListener(fillInBookInfo);

function toggleDl(element) {
    // + to convert to int
    let ei_id = Number(this.dataset.eiId);
    let before = document.getElementById("Downloaded").innerText;
    browser.runtime.sendMessage({
        action: "toggle_dl",
        ei_id: ei_id,
        before: before
    });
}
document.getElementById("toggle-dl").addEventListener("click", toggleDl);
function toggleFav(element) {
    // + to convert to int
    let book_id = Number(this.dataset.book_id);
    let before = document.getElementById("Favorite").innerText;
    browser.runtime.sendMessage({
        action: "toggle_fav",
        book_id: book_id,
        before: before
    });
}
document.getElementById("toggle-fav").addEventListener("click", toggleFav);
document.getElementById("List").addEventListener("mouseover", function(event) {
    event.currentTarget.disabled = false;
});
document.getElementById("List").addEventListener("focusout", function(event) {
    event.currentTarget.disabled = true;
    // Number(x) is same as doing +x
    let book_id = Number(event.currentTarget.dataset.book_id);
    let before = event.currentTarget.dataset.before;
    let after = event.currentTarget.value;
    browser.runtime.sendMessage({
        action: "set_lists",
        book_id: book_id,
        before: before,
        after: after
    });
});
