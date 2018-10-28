function getBookInfo() {
    var title = document.querySelector("#Title").innerText;
    var url = window.location.href;
    var result = [url, title];
    return result;
}

function sendBookInfo() {
    book_info = getBookInfo();
    console.log(book_info);
    browser.runtime.sendMessage({
        action: "get_book_info",
        book_info: book_info
    });
}

sendBookInfo();
