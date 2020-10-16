$(document).ready(function() {
    // Check for click events on the navbar burger icon
    $(".navbar-burger").click(function() {
        // Toggle the "is-active" class on both the "navbar-burger" and the "navbar-menu"
        $(".navbar-burger").toggleClass("is-active");
        $(".navbar-menu").toggleClass("is-active");

        // toggle hidden description of items
        // .menu-description .vis-toggle -> tag with .vis-toggle somwhere below .menu..
        // .menu-description.vis-toggle -> tag with both classes
        $(".navbar-menu .menu-description.vis-toggle").toggleClass("is-hidden");
    });

    // remove is-active when burger-menu is hidden with css media breakpoints
    let mediaQuery = window.matchMedia("(min-width: 1024px)");  // desktop
    mediaQuery.addListener((mq) => {
        if (mq.matches) {
            $(".navbar-burger").removeClass("is-active");
            $(".navbar-menu").removeClass("is-active");
            $(".navbar-menu .menu-description.vis-toggle").addClass("is-hidden");
        }
    }); // Attach listener function on state changes

    $(".navbar-dropdown .dropdown").click(function(e) {
        $(e.currentTarget).toggleClass("is-active");
    });

    function setSortCol(e) {
        let new_sort_col = $(e.currentTarget).data("value");
        $("input[name=sort_col]").val(new_sort_col);

        $("#sortColOptions .dropdown-item.is-active").removeClass("is-active");
        $(e.currentTarget).addClass("is-active");
        
        e.preventDefault();
        return
    }

    $("#sortColOptions .dropdown-item").click(setSortCol);

    function changeOrder(e) {
        let order_div = $(e.currentTarget);
        let current_order = order_div.data("value");
        console.log(order_div, current_order);
        let new_order = "";
        if (current_order === "DESC") {
            new_order = "ASC";
            order_div.find("span.icon").html('<i class="fas fa-sort-amount-up"></i>');
            order_div.find("span.menu-description").html('Sort: Ascending');
        } else {
            new_order = "DESC";
            order_div.find("span.icon").html('<i class="fas fa-sort-amount-down"></i>');
            order_div.find("span.menu-description").html('Sort: Descending');
        }
        $("input[name=order]").val(new_order);
        // data-value update isnt shown in chrome debugger but it works correctly
        console.log("after:", new_order, order_div);
        order_div.data("value", new_order);

        e.preventDefault();
        return
    }

    $("#orderLnk").click(changeOrder);
    /* An arrow function expression has a shorter syntax compared to
    function expressions and lexically binds the this value (does not bind
    its own this, arguments, super, or new.target). Arrow functions are
    always anonymous. */
    $("#refreshSearch").click((e) => {
        e.preventDefault();
        $("#searchForm").submit()
        return
    });
});
