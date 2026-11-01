import test from 'node:test';
import assert from 'node:assert/strict';
import {placeInlineTools} from './inlineTools.mjs';

test('toolbar stays near text and within the visible window',()=>{
 assert.deepEqual(placeInlineTools({left:100,top:300,bottom:320},600,90,1000,800),{left:100,top:200});
 assert.deepEqual(placeInlineTools({left:900,top:20,bottom:40},600,90,1000,800),{left:392,top:50});
 assert.deepEqual(placeInlineTools({left:-50,top:790,bottom:810},300,90,320,800),{left:8,top:690});
});
