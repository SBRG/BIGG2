
$(function() {
  function getParameterByName(name) {
    name = name.replace(/[\[]/, "\\[").replace(/[\]]/, "\\]");
    var regex = new RegExp("[\\?&]" + name + "=([^&#]*)"),
        results = regex.exec(location.search);
    return results === null ? "" : decodeURIComponent(results[1].replace(/\+/g, " "));
}
 tablelist = ['.summary-reactions-tablesorter', '.individual-reactions-tablesorter', '.summary-metabolites-tablesorter', '.summary-models-tablesorter', '.summary-genes-tablesorter']
 for(var i =0; i < tablelist.length; i++){

  $(tablelist[i])
  .tablesorter({
    widthFixed: true,
    sortMultiSortKey: null,
        // default sort
        sortList: [[0, 0]]
      })
  .tablesorterPager({

      // **********************************
      //  Description of ALL pager options
      // **********************************

      // target the pager markup - see the HTML block below
      container: $(tablelist[i] + " .pager"),

      // use this format: "http:/mydatabase.com?page={page}&size={size}&{sortList:col}"
      // where {page} is replaced by the page number (or use {page+1} to get a one-based index),
      // {size} is replaced by the number of records to show,
      // {sortList:col} adds the sortList to the url into a "col" array, and {filterList:fcol} adds
      // the filterList to the url into an "fcol" array.
      // So a sortList = [[2,0],[3,0]] becomes "&col[2]=0&col[3]=0" in the url
      // and a filterList = [[2,Blue],[3,13]] becomes "&fcol[2]=Blue&fcol[3]=13" in the url
      ajaxUrl : '/api/v2'+window.location.pathname+'?query='+getParameterByName('query')+'&page={page}&size={size}&{sortList:col}',

      // modify the url after all processing has been applied
      customAjaxUrl: function(table, url) {
          // manipulate the url string as you desire
          url += '&cPage=' + $(table).attr('class').split(' ')[0].split('-')[1];
          // trigger my custom event
          $(table).trigger('changingUrl', url);
          // send the server the current page
          return url;
        },

      // add more ajax settings here
      // see http://api.jquery.com/jQuery.ajax/#jQuery-ajax-settings
      ajaxObject: {
        dataType: 'json'
      },

      // process ajax so that the following information is returned:
      // [ total_rows (number), rows (array of arrays), headers (array; optional) ]
      // example:
      // [
      //   100,  // total rows
      //   [
      //     [ "row1cell1", "row1cell2", ... "row1cellN" ],
      //     [ "row2cell1", "row2cell2", ... "row2cellN" ],
      //     ...
      //     [ "rowNcell1", "rowNcell2", ... "rowNcellN" ]
      //   ],
      //   [ "header1", "header2", ... "headerN" ] // optional
      // ]
      // OR
      // return [ total_rows, $rows (jQuery object; optional), headers (array; optional) ]
      ajaxProcessing: function(data) {
        if (data && data.hasOwnProperty('rows')) {
          var indx, r, row, c, d = data.rows,
          // total number of rows (required)
          total = data.total_rows,
          // array of header names (optional)
          headers = data.headers,
          // cross-reference to match JSON key within data (no spaces)
          headerXref = headers.join(',').replace(/\s+/g,'').split(','),
          // all rows: array of arrays; each internal array has the table cell data for that row
          rows = [],
          // len should match pager set size (c.size)
          len = d.length;
          // this will depend on how the json is set up - see City0.json
          // rows
          for ( r=0; r < len; r++ ) {
            row = []; // new row array
            // cells
            for ( c in d[r] ) {
              if (typeof(c) === "string") {
                // match the key with the header to get the proper column index
                indx = $.inArray( c, headerXref );
                // add each table cell data to row array
                if (indx >= 0) {
                  row[indx] = d[r][c];
                }
              }
            }
            rows.push(row); // add new row array to rows array
          }

          // in version 2.10, you can optionally return $(rows) a set of table rows within a jQuery object
          return [ total, rows ];
        }
      },

      // Set this option to false if your table data is preloaded into the table, but you are still using ajax
      processAjaxOnInit: true,

      // output string - default is '{page}/{totalPages}';
      // possible variables: {page}, {totalPages}, {startRow}, {endRow} and {totalRows}
      output: '{startRow} to {endRow} ({totalRows})',

      // apply disabled classname (cssDisabled option) to the pager arrows when the rows
      // are at either extreme is visible; default is true
      updateArrows: true,

      // starting page of the pager (zero based index)
      page: 0,

      // Number of visible rows - default is 10
      size: 100,

      // Saves the current pager page size and number (requires storage widget)
      savePages: false,

      // Saves tablesorter paging to custom key if defined.
      // Key parameter name used by the $.tablesorter.storage function.
      // Useful if you have multiple tables defined
      // storageKey: 'tablesorter-pager',

      // Reset pager to this page after filtering; set to desired page number (zero-based index),
      // or false to not change page at filter start
      pageReset: false,

      // if true, the table will remain the same height no matter how many records are displayed.
      // The space is made up by an empty table row set to a height to compensate; default is false
      fixedHeight: false,

      // remove rows from the table to speed up the sort of large tables.
      // setting this to false, only hides the non-visible rows; needed if you plan to
      // add/remove rows with the pager e// nabled.
      removeRows: false,

      // If true, child rows will be counted towards the pager set size
      countChildRows: false,

      // css class names of pager arrows
      cssNext        : '.next',  // next page arrow
      cssPrev        : '.prev',  // previous page arrow
      cssFirst       : '.first', // go to first page arrow
      cssLast        : '.last',  // go to last page arrow
      cssGoto        : '.gotoPage', // page select dropdown - select dropdown that set the "page" option

      cssPageDisplay : '.pagedisplay', // location of where the "output" is displayed
      cssPageSize    : '.pagesize', // page size selector - select dropdown that sets the "size" option

      // class added to arrows when at the extremes; see the "updateArrows" option
      // (i.e. prev/first arrows are "disabled" when on the first page)
      cssDisabled    : 'disabled', // Note there is no period "." in front of this class name
      cssErrorRow    : 'tablesorter-errorRow' // error information row

    });

    
    }
      
});