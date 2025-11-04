//Maya ASCII 2026 scene
//Name: BaseFeatures.ma
//Last modified: Fri, Oct 31, 2025 03:14:03 PM
//Codeset: 932
requires maya "2026";
requires -nodeType "aiOptions" -nodeType "aiAOVDriver" -nodeType "aiAOVFilter" -nodeType "aiImagerDenoiserOidn"
		 "mtoa" "5.5.0";
currentUnit -l centimeter -a degree -t film;
fileInfo "application" "maya";
fileInfo "product" "Maya 2026";
fileInfo "version" "2026";
fileInfo "cutIdentifier" "202502240946-c910a8ba47";
fileInfo "osv" "Windows 11 Education v2009 (Build: 26100)";
fileInfo "UUID" "5D8379CB-4AB8-F3CE-FB62-3FB8D84D2C6E";
createNode transform -s -n "persp";
	rename -uid "21769BCC-4EDC-3DB6-6F9C-818C69CFD12F";
	setAttr ".v" no;
	setAttr ".t" -type "double3" -5.2964810664272362 5.2190647349323722 18.290274615301669 ;
	setAttr ".r" -type "double3" -24.938352729347834 328.20000000003881 -2.8067261088141918e-15 ;
createNode camera -s -n "perspShape" -p "persp";
	rename -uid "FE36C0B3-4BE9-9802-A85B-69BFC69E1CF4";
	setAttr -k off ".v" no;
	setAttr ".fl" 34.999999999999993;
	setAttr ".coi" 9.4741527919152233;
	setAttr ".imn" -type "string" "persp";
	setAttr ".den" -type "string" "persp_depth";
	setAttr ".man" -type "string" "persp_mask";
	setAttr ".tp" -type "double3" 0 -2.4651903288156619e-32 10.032998719208933 ;
	setAttr ".hc" -type "string" "viewSet -p %camera";
createNode transform -s -n "top";
	rename -uid "7CDB2DC0-469B-D714-0210-A383A48E9013";
	setAttr ".v" no;
	setAttr ".t" -type "double3" 0 1000.1 0 ;
	setAttr ".r" -type "double3" -90 0 0 ;
createNode camera -s -n "topShape" -p "top";
	rename -uid "8C13B4FA-4F6F-C9E0-DD2C-808FD108228E";
	setAttr -k off ".v" no;
	setAttr ".rnd" no;
	setAttr ".coi" 1000.1;
	setAttr ".ow" 30;
	setAttr ".imn" -type "string" "top";
	setAttr ".den" -type "string" "top_depth";
	setAttr ".man" -type "string" "top_mask";
	setAttr ".hc" -type "string" "viewSet -t %camera";
	setAttr ".o" yes;
	setAttr ".ai_translator" -type "string" "orthographic";
createNode transform -s -n "front";
	rename -uid "30068F7D-491C-D8CB-CCD7-D69DA7FE6C82";
	setAttr ".v" no;
	setAttr ".t" -type "double3" -0.18211682395570045 2.0882032528784897 1000.1009882865527 ;
createNode camera -s -n "frontShape" -p "front";
	rename -uid "3E192FD6-41AC-EC50-516B-658D7E74E628";
	setAttr -k off ".v" no;
	setAttr ".rnd" no;
	setAttr ".coi" 1000.1009882865527;
	setAttr ".ow" 10.191907559768605;
	setAttr ".imn" -type "string" "front";
	setAttr ".den" -type "string" "front_depth";
	setAttr ".man" -type "string" "front_mask";
	setAttr ".tp" -type "double3" 0 1.4059771474929659 3.3306690738754696e-16 ;
	setAttr ".hc" -type "string" "viewSet -f %camera";
	setAttr ".o" yes;
	setAttr ".ai_translator" -type "string" "orthographic";
createNode transform -s -n "side";
	rename -uid "E83F2391-4AFB-D764-9782-09AB946F7394";
	setAttr ".v" no;
	setAttr ".t" -type "double3" 1000.1299814420416 1.5057570990842337 -7.8881437583537419 ;
	setAttr ".r" -type "double3" 0 90 0 ;
createNode camera -s -n "sideShape" -p "side";
	rename -uid "7C93660B-4867-E9D2-97F7-27AE1E5ABB33";
	setAttr -k off ".v" no;
	setAttr ".rnd" no;
	setAttr ".coi" 1000.1299814420416;
	setAttr ".ow" 11.331897711393916;
	setAttr ".imn" -type "string" "side";
	setAttr ".den" -type "string" "side_depth";
	setAttr ".man" -type "string" "side_mask";
	setAttr ".tp" -type "double3" 0 -2.4651903288156619e-32 -8 ;
	setAttr ".hc" -type "string" "viewSet -s %camera";
	setAttr ".o" yes;
	setAttr ".ai_translator" -type "string" "orthographic";
createNode transform -n "IK_model";
	rename -uid "FAF3D0EB-4B6E-5AB0-8310-FDB82EE9719F";
	setAttr ".rp" -type "double3" 0 0 3 ;
	setAttr ".sp" -type "double3" 0 0 3 ;
createNode joint -n "IK_basejoint4" -p "IK_model";
	rename -uid "434ECCFA-464B-C832-6680-8F971EF92726";
	setAttr ".t" -type "double3" 0 4 3 ;
	setAttr ".r" -type "double3" 1.0224522289189493e-30 1.4033418597069752e-14 7.0930724470916261e-31 ;
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
createNode nurbsCurve -n "center_IK_CTRL1Shape" -p "IK_basejoint4";
	rename -uid "E819F137-4E53-6BA2-25B7-D79C88FC7A80";
	setAttr -k off ".v";
	setAttr ".cc" -type "nurbsCurve" 
		3 8 2 no 3
		13 -2 -1 0 1 2 3 4 5 6 7 8 9 10
		11
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		-1.1081941875543881 3.5177356190060272e-33 -5.7448982375248304e-17
		-0.78361162489122449 -4.7982373409884725e-17 0.78361162489122449
		-1.1100856969603225e-16 -6.7857323231109171e-17 1.1081941875543884
		0.78361162489122449 -4.7982373409884719e-17 0.78361162489122438
		1.1081941875543881 -9.2536792101100989e-33 1.511240500779959e-16
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		;
createNode joint -n "IK_basejoint2" -p "IK_basejoint4";
	rename -uid "10957613-4039-1822-CF27-D69479232105";
	setAttr ".t" -type "double3" -0.099981427882084598 -2 -2.0217660858695382e-16 ;
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
createNode nurbsCurve -n "center_IK_CTRL2Shape" -p "IK_basejoint2";
	rename -uid "AC73BA3B-4608-2BBB-4312-BAAEB3B39688";
	setAttr -k off ".v";
	setAttr ".cc" -type "nurbsCurve" 
		3 8 2 no 3
		13 -2 -1 0 1 2 3 4 5 6 7 8 9 10
		11
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		-1.1081941875543881 3.5177356190060272e-33 -5.7448982375248304e-17
		-0.78361162489122449 -4.7982373409884725e-17 0.78361162489122449
		-1.1100856969603225e-16 -6.7857323231109171e-17 1.1081941875543884
		0.78361162489122449 -4.7982373409884719e-17 0.78361162489122438
		1.1081941875543881 -9.2536792101100989e-33 1.511240500779959e-16
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		;
createNode joint -n "IK_basejoint3" -p "IK_basejoint2";
	rename -uid "8185788D-4003-A093-787C-19A1B0EB1EA9";
	setAttr ".t" -type "double3" 0.099981427882084306 -2 0 ;
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
createNode nurbsCurve -n "center_IK_CTRL3Shape" -p "IK_basejoint3";
	rename -uid "B1DD9387-4E7E-ABAA-737F-2A9F6CA37D9F";
	setAttr -k off ".v";
	setAttr ".cc" -type "nurbsCurve" 
		3 8 2 no 3
		13 -2 -1 0 1 2 3 4 5 6 7 8 9 10
		11
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		-1.1081941875543881 3.5177356190060272e-33 -5.7448982375248304e-17
		-0.78361162489122449 -4.7982373409884725e-17 0.78361162489122449
		-1.1100856969603225e-16 -6.7857323231109171e-17 1.1081941875543884
		0.78361162489122449 -4.7982373409884719e-17 0.78361162489122438
		1.1081941875543881 -9.2536792101100989e-33 1.511240500779959e-16
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		;
createNode ikEffector -n "effector1" -p "IK_basejoint2";
	rename -uid "B500AF51-4D0F-80B2-E9B0-25B40DF4A0EC";
	setAttr ".v" no;
	setAttr ".hd" yes;
createNode joint -n "IK_basejoint5" -p "IK_model";
	rename -uid "A34741F4-414D-7F9E-ACD0-5AB751EF064B";
	setAttr ".t" -type "double3" 0 0 3 ;
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
createNode nurbsCurve -n "center_IK_CTRL1Shape" -p "IK_basejoint5";
	rename -uid "1EC0E77F-4250-7292-A372-9B85316BB7B3";
	setAttr -k off ".v";
	setAttr ".cc" -type "nurbsCurve" 
		3 8 2 no 3
		13 -2 -1 0 1 2 3 4 5 6 7 8 9 10
		11
		1.2140552221407817 6.1584915928151995e-17 -1.2140552221407817
		1.0283110214264612e-16 8.7094223343199387e-17 -1.2140593881267288
		-1.2140552221407817 6.1584915928151983e-17 -1.2140552221407817
		-1.2140593881267288 1.1503557989351276e-32 -7.3735217712442277e-17
		-1.2140552221407817 -6.1584915928151983e-17 1.2140552221407817
		-1.2674155538793313e-16 -8.7094223343199437e-17 1.2140593881267285
		1.2140552221407817 -6.1584915928151983e-17 1.2140552221407817
		1.2140593881267285 -4.8884304147204647e-33 1.9396626838925626e-16
		1.2140552221407817 6.1584915928151995e-17 -1.2140552221407817
		1.0283110214264612e-16 8.7094223343199387e-17 -1.2140593881267288
		-1.2140552221407817 6.1584915928151983e-17 -1.2140552221407817
		;
createNode ikHandle -n "ikHandle1" -p "IK_basejoint5";
	rename -uid "C7213066-46FE-04CC-4140-1286DE787026";
	setAttr ".pv" -type "double3" -1.026188 0 0 ;
	setAttr ".roc" yes;
createNode transform -n "FK_model";
	rename -uid "A8ADA957-45E9-F637-52BB-89B549FE98E9";
createNode joint -n "FK_basejoint1" -p "FK_model";
	rename -uid "89607CA0-43E3-FE15-FF7C-B183FAABA52B";
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
	setAttr ".opm" -type "matrix" 1 0 0 0 0 1 0 0 0 0 1 0 0 4 0 1;
createNode nurbsCurve -n "center_FK_CTRL1Shape" -p "FK_basejoint1";
	rename -uid "53247098-4A0E-F128-8536-B3B9CD20C896";
	setAttr -k off ".v";
	setAttr ".cc" -type "nurbsCurve" 
		3 8 2 no 3
		13 -2 -1 0 1 2 3 4 5 6 7 8 9 10
		11
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		-1.1081941875543881 3.5177356190060272e-33 -5.7448982375248304e-17
		-0.78361162489122449 -4.7982373409884725e-17 0.78361162489122449
		-1.1100856969603225e-16 -6.7857323231109171e-17 1.1081941875543884
		0.78361162489122449 -4.7982373409884719e-17 0.78361162489122438
		1.1081941875543881 -9.2536792101100989e-33 1.511240500779959e-16
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		;
createNode joint -n "FK_basejoint2" -p "FK_basejoint1";
	rename -uid "94ACB297-4E3D-3A71-8D91-2989C0B337CB";
	setAttr ".t" -type "double3" -0.099981427882084306 -2 0 ;
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
createNode nurbsCurve -n "center_FK_CTRL2Shape" -p "FK_basejoint2";
	rename -uid "A524862D-4B7F-CCB7-562C-489F9872BCF7";
	setAttr -k off ".v";
	setAttr ".cc" -type "nurbsCurve" 
		3 8 2 no 3
		13 -2 -1 0 1 2 3 4 5 6 7 8 9 10
		11
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		-1.1081941875543881 3.5177356190060272e-33 -5.7448982375248304e-17
		-0.78361162489122449 -4.7982373409884725e-17 0.78361162489122449
		-1.1100856969603225e-16 -6.7857323231109171e-17 1.1081941875543884
		0.78361162489122449 -4.7982373409884719e-17 0.78361162489122438
		1.1081941875543881 -9.2536792101100989e-33 1.511240500779959e-16
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		;
createNode joint -n "FK_basejoint3" -p "FK_basejoint2";
	rename -uid "F06BA501-46FC-9DE9-3A75-7EA31BC68515";
	setAttr ".t" -type "double3" 0.099981427882084306 -2 0 ;
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
createNode nurbsCurve -n "center_FK_CTRL3Shape" -p "FK_basejoint3";
	rename -uid "4E2243F4-4C82-8A24-D2C8-4D9BFF7496D6";
	setAttr -k off ".v";
	setAttr ".cc" -type "nurbsCurve" 
		3 8 2 no 3
		13 -2 -1 0 1 2 3 4 5 6 7 8 9 10
		11
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		-1.1081941875543881 3.5177356190060272e-33 -5.7448982375248304e-17
		-0.78361162489122449 -4.7982373409884725e-17 0.78361162489122449
		-1.1100856969603225e-16 -6.7857323231109171e-17 1.1081941875543884
		0.78361162489122449 -4.7982373409884719e-17 0.78361162489122438
		1.1081941875543881 -9.2536792101100989e-33 1.511240500779959e-16
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		;
createNode joint -n "CustomControlAttributes";
	rename -uid "F68581E5-4FDF-13EC-9D91-13B0A43139AB";
	addAttr -ci true -sn "Vector" -ln "Vector" -at "double3" -nc 3;
	addAttr -ci true -sn "VectorX" -ln "VectorX" -at "double" -p "Vector";
	addAttr -ci true -sn "VectorY" -ln "VectorY" -at "double" -p "Vector";
	addAttr -ci true -sn "VectorZ" -ln "VectorZ" -at "double" -p "Vector";
	addAttr -ci true -sn "Integer" -ln "Integer" -min 0 -max 10 -at "long";
	addAttr -ci true -sn "String" -ln "String" -dt "string";
	addAttr -ci true -sn "Float" -ln "Float" -min 0 -max 10 -at "double";
	addAttr -ci true -sn "Boolean" -ln "Boolean" -min 0 -max 1 -at "bool";
	addAttr -ci true -sn "Enum" -ln "Enum" -min 0 -max 1 -en "Green:Blue" -at "enum";
	setAttr ".t" -type "double3" 0 0 -3 ;
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
	setAttr -k on ".Vector";
	setAttr -k on ".VectorX";
	setAttr -k on ".VectorY";
	setAttr -k on ".VectorZ";
	setAttr -k on ".Integer";
	setAttr -k on ".String";
	setAttr -k on ".Float";
	setAttr -k on ".Boolean";
	setAttr -k on ".Enum";
createNode nurbsCurve -n "center_CTRL1Shape" -p "CustomControlAttributes";
	rename -uid "34C22A54-43B2-5370-1281-D69A8E01C8F7";
	setAttr -k off ".v";
	setAttr ".cc" -type "nurbsCurve" 
		3 8 2 no 3
		13 -2 -1 0 1 2 3 4 5 6 7 8 9 10
		11
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		-1.1081941875543881 3.5177356190060272e-33 -5.7448982375248304e-17
		-0.78361162489122449 -4.7982373409884725e-17 0.78361162489122449
		-1.1100856969603225e-16 -6.7857323231109171e-17 1.1081941875543884
		0.78361162489122449 -4.7982373409884719e-17 0.78361162489122438
		1.1081941875543881 -9.2536792101100989e-33 1.511240500779959e-16
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		;
createNode transform -n "IKFK_BindJoint_model";
	rename -uid "C06A83FF-4A7B-26CA-5A72-6D98D5033B1C";
	setAttr ".rp" -type "double3" 0 0 6 ;
	setAttr ".sp" -type "double3" 0 0 6 ;
createNode joint -n "basebindjoint1" -p "IKFK_BindJoint_model";
	rename -uid "2F7E87CD-4DD9-EA5F-2500-C9A3184952DA";
	setAttr ".t" -type "double3" 0 4 6 ;
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
createNode joint -n "basebindjoint2" -p "basebindjoint1";
	rename -uid "05FD0D24-4265-0B09-EC63-83B21FFFA080";
	setAttr ".t" -type "double3" -0.099981427882084306 -2 0 ;
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
createNode joint -n "basebindjoint3" -p "basebindjoint2";
	rename -uid "88D036B4-403C-2F73-AB37-26A720E132AB";
	setAttr ".t" -type "double3" 0.099981427882084306 -2 0 ;
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
createNode joint -n "IKFK_SwitchCTRL" -p "IKFK_BindJoint_model";
	rename -uid "5C7F3E66-4CEA-2A05-9722-368B9D7B8B9A";
	addAttr -ci true -sn "IKFK_Switch" -ln "IKFK_Switch" -min 0 -max 1 -at "double";
	setAttr ".ove" yes;
	setAttr ".ovc" 17;
	setAttr ".t" -type "double3" 0 5 6 ;
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
	setAttr ".ds" 2;
	setAttr -k on ".IKFK_Switch" 1;
createNode nurbsCurve -n "center_CTRL2Shape" -p "IKFK_SwitchCTRL";
	rename -uid "A9834B2C-4156-CB52-E84E-84BBDFA35255";
	setAttr -k off ".v";
	setAttr ".cc" -type "nurbsCurve" 
		3 8 2 no 3
		13 -2 -1 0 1 2 3 4 5 6 7 8 9 10
		11
		-7.0198243769401299e-18 0.19818778261502251 -0.19818778261502251
		-5.8226731241071261e-17 5.8226731241071261e-17 -0.95091468465211304
		-7.0198243769401299e-18 -0.19818778261502246 -0.19818778261502246
		-4.7632779038697819e-17 -0.95091468465211304 -4.9295585171315445e-17
		7.0198243769401299e-18 -0.19818778261502251 0.19818778261502251
		5.8226731241071422e-17 -9.5253774321933862e-17 0.95091468465211304
		7.0198243769401299e-18 0.19818778261502246 0.19818778261502246
		4.7632779038697819e-17 0.95091468465211304 1.2967589979911794e-16
		-7.0198243769401299e-18 0.19818778261502251 -0.19818778261502251
		-5.8226731241071261e-17 5.8226731241071261e-17 -0.95091468465211304
		-7.0198243769401299e-18 -0.19818778261502246 -0.19818778261502246
		;
createNode transform -n "Blendshape_model";
	rename -uid "FCF69D54-4F0E-7DE6-881F-E98FEEAF04A3";
	setAttr ".rp" -type "double3" 0 0 -5 ;
	setAttr ".sp" -type "double3" 0 0 -5 ;
createNode transform -n "BlendshapeResult" -p "Blendshape_model";
	rename -uid "3D52858C-41F8-3EF7-E5B5-FF934658E70D";
	setAttr ".t" -type "double3" 0 0 -1 ;
	setAttr ".rp" -type "double3" 0 0 -5 ;
	setAttr ".sp" -type "double3" 0 0 -5 ;
createNode mesh -n "BlendshapeResultShape" -p "BlendshapeResult";
	rename -uid "4090496E-4C65-8C51-7E4E-788B6A76D7DF";
	setAttr -k off ".v";
	setAttr ".vir" yes;
	setAttr ".vif" yes;
	setAttr -s 6 ".gtag";
	setAttr ".gtag[0].gtagnm" -type "string" "back";
	setAttr ".gtag[0].gtagcmp" -type "componentList" 3 "f[2]" "f[12]" "f[20:21]";
	setAttr ".gtag[1].gtagnm" -type "string" "bottom";
	setAttr ".gtag[1].gtagcmp" -type "componentList" 3 "f[3]" "f[7]" "f[22:23]";
	setAttr ".gtag[2].gtagnm" -type "string" "front";
	setAttr ".gtag[2].gtagcmp" -type "componentList" 2 "f[0]" "f[15:17]";
	setAttr ".gtag[3].gtagnm" -type "string" "left";
	setAttr ".gtag[3].gtagcmp" -type "componentList" 2 "f[5:6]" "f[10:11]";
	setAttr ".gtag[4].gtagnm" -type "string" "right";
	setAttr ".gtag[4].gtagcmp" -type "componentList" 3 "f[4]" "f[8]" "f[13:14]";
	setAttr ".gtag[5].gtagnm" -type "string" "top";
	setAttr ".gtag[5].gtagcmp" -type "componentList" 3 "f[1]" "f[9]" "f[18:19]";
	setAttr ".pv" -type "double2" 0.5 0.5 ;
	setAttr ".uvst[0].uvsn" -type "string" "map1";
	setAttr -s 39 ".uvst[0].uvsp[0:38]" -type "float2" 0.375 0 0.625 0 0.375
		 0.25 0.625 0.25 0.375 0.5 0.625 0.5 0.375 0.75 0.625 0.75 0.375 1 0.625 1 0.875 0
		 0.875 0.25 0.125 0 0.125 0.25 0.25 0.25 0.375 0.375 0.25 0 0.375 0.875 0.625 0.875
		 0.75 0 0.625 0.375 0.75 0.25 0.375 0.125 0.25 0.125 0.125 0.125 0.375 0.625 0.625
		 0.625 0.875 0.125 0.75 0.125 0.625 0.125 0.5 0 0.5 1 0.5 0.125 0.5 0.25 0.5 0.375
		 0.5 0.5 0.5 0.625 0.5 0.75 0.5 0.875;
	setAttr ".cuvs" -type "string" "map1";
	setAttr ".dcc" -type "string" "Ambient+Diffuse";
	setAttr ".covm[0]"  0 1 1;
	setAttr ".cdvm[0]"  0 1 1;
	setAttr -s 26 ".pt[0:25]" -type "float3"  0.22222221 0.72222221 -5.2222223 
		-0.22222221 0.72222221 -5.2222223 0.22222221 0.27777779 -5.2222223 -0.22222221 0.27777779 
		-5.2222223 0.22222221 0.27777779 -4.7777777 -0.22222221 0.27777779 -4.7777777 0.22222221 
		0.72222221 -4.7777777 -0.22222221 0.72222221 -4.7777777 0.125 0.375 -5 0.125 0.625 
		-5 -0.125 0.625 -5 -0.125 0.375 -5 0.125 0.5 -5.125 -1.1435297e-14 0.5 -5 0.125 0.5 
		-4.875 -0.125 0.5 -4.875 1.1435297e-14 0.5 -5 -0.125 0.5 -5.125 0 0.625 -5.125 0 
		0.5 -5 0 0.375 -5.125 0 0.5 -5 0 0.375 -4.875 0 0.5 -5 0 0.625 -4.875 0 0.5 -5;
	setAttr -s 26 ".vt[0:25]"  -0.5 -0.5 0.5 0.5 -0.5 0.5 -0.5 0.5 0.5 0.5 0.5 0.5
		 -0.5 0.5 -0.5 0.5 0.5 -0.5 -0.5 -0.5 -0.5 0.5 -0.5 -0.5 -0.5 0.5 0 -0.5 -0.5 0 0.5 -0.5 0
		 0.5 0.5 0 -0.5 0 0.5 -0.5 0 0 -0.5 0 -0.5 0.5 0 -0.5 0.5 0 0 0.5 0 0.5 0 -0.5 0.5
		 0 0 0.5 0 0.5 0.5 0 0.5 0 0 0.5 -0.5 0 0 -0.5 0 -0.5 -0.5 0 -0.5 0;
	setAttr -s 48 ".ed[0:47]"  0 18 0 2 20 0 4 22 0 6 24 0 0 12 0 1 17 0
		 2 8 0 3 11 0 4 14 0 5 15 0 6 9 0 7 10 0 8 4 0 9 0 0 10 1 0 11 5 0 8 13 1 9 25 1 10 16 1
		 11 21 1 12 2 0 13 9 1 14 6 0 15 7 0 16 11 1 17 3 0 12 13 1 13 14 1 14 23 1 15 16 1
		 16 17 1 17 19 1 18 1 0 19 12 1 20 3 0 21 8 1 22 5 0 23 15 1 24 7 0 25 10 1 18 19 1
		 19 20 1 20 21 1 21 22 1 22 23 1 23 24 1 24 25 1 25 18 1;
	setAttr -s 24 -ch 96 ".fc[0:23]" -type "polyFaces" 
		f 4 0 40 33 -5
		mu 0 4 0 30 32 22
		f 4 1 42 35 -7
		mu 0 4 2 33 34 15
		f 4 28 45 -4 -23
		mu 0 4 25 36 37 6
		f 4 17 47 -1 -14
		mu 0 4 17 38 31 8
		f 4 -15 18 30 -6
		mu 0 4 1 19 28 29
		f 4 26 21 13 4
		mu 0 4 22 23 16 0
		f 4 10 -22 27 22
		mu 0 4 12 16 23 24
		f 4 3 46 -18 -11
		mu 0 4 6 37 38 17
		f 4 29 -19 -12 -24
		mu 0 4 27 28 19 10
		f 4 -36 43 -3 -13
		mu 0 4 15 34 35 4
		f 4 16 -27 20 6
		mu 0 4 14 23 22 2
		f 4 -28 -17 12 8
		mu 0 4 24 23 14 13
		f 4 2 44 -29 -9
		mu 0 4 4 35 36 25
		f 4 -25 -30 -10 -16
		mu 0 4 21 28 27 11
		f 4 -31 24 -8 -26
		mu 0 4 29 28 21 3
		f 4 -34 41 -2 -21
		mu 0 4 22 32 33 2
		f 4 -41 32 5 31
		mu 0 4 32 30 1 29
		f 4 -42 -32 25 -35
		mu 0 4 33 32 29 3
		f 4 -43 34 7 19
		mu 0 4 34 33 3 20
		f 4 -44 -20 15 -37
		mu 0 4 35 34 20 5
		f 4 -45 36 9 -38
		mu 0 4 36 35 5 26
		f 4 -46 37 23 -39
		mu 0 4 37 36 26 7
		f 4 -47 38 11 -40
		mu 0 4 38 37 7 18
		f 4 -48 39 14 -33
		mu 0 4 31 38 18 9;
	setAttr ".cd" -type "dataPolyComponent" Index_Data Edge 0 ;
	setAttr ".cvd" -type "dataPolyComponent" Index_Data Vertex 0 ;
	setAttr ".pd[0]" -type "dataPolyComponent" Index_Data UV 0 ;
	setAttr ".hfd" -type "dataPolyComponent" Index_Data Face 0 ;
createNode transform -n "BlendshapeBase" -p "Blendshape_model";
	rename -uid "BA0EB3B1-4B85-FC82-651A-68B881783671";
	setAttr ".rp" -type "double3" 0 0 -5 ;
	setAttr ".sp" -type "double3" 0 0 -5 ;
createNode mesh -n "BlendshapeBaseShape" -p "BlendshapeBase";
	rename -uid "6428F5E1-47F1-F2C7-BC34-0EBD337756CE";
	setAttr -k off ".v";
	setAttr ".vir" yes;
	setAttr ".vif" yes;
	setAttr ".pv" -type "double2" 0.5 0.5 ;
	setAttr ".uvst[0].uvsn" -type "string" "map1";
	setAttr ".cuvs" -type "string" "map1";
	setAttr ".dcc" -type "string" "Ambient+Diffuse";
	setAttr ".covm[0]"  0 1 1;
	setAttr ".cdvm[0]"  0 1 1;
createNode mesh -n "BlendshapeBaseShape3Orig" -p "BlendshapeBase";
	rename -uid "EF5A339D-4D0E-5D3E-9264-5794049516E6";
	setAttr -k off ".v";
	setAttr ".io" yes;
	setAttr ".vir" yes;
	setAttr ".vif" yes;
	setAttr -s 6 ".gtag";
	setAttr ".gtag[0].gtagnm" -type "string" "back";
	setAttr ".gtag[0].gtagcmp" -type "componentList" 3 "f[2]" "f[12]" "f[20:21]";
	setAttr ".gtag[1].gtagnm" -type "string" "bottom";
	setAttr ".gtag[1].gtagcmp" -type "componentList" 3 "f[3]" "f[7]" "f[22:23]";
	setAttr ".gtag[2].gtagnm" -type "string" "front";
	setAttr ".gtag[2].gtagcmp" -type "componentList" 2 "f[0]" "f[15:17]";
	setAttr ".gtag[3].gtagnm" -type "string" "left";
	setAttr ".gtag[3].gtagcmp" -type "componentList" 2 "f[5:6]" "f[10:11]";
	setAttr ".gtag[4].gtagnm" -type "string" "right";
	setAttr ".gtag[4].gtagcmp" -type "componentList" 3 "f[4]" "f[8]" "f[13:14]";
	setAttr ".gtag[5].gtagnm" -type "string" "top";
	setAttr ".gtag[5].gtagcmp" -type "componentList" 3 "f[1]" "f[9]" "f[18:19]";
	setAttr ".uvst[0].uvsn" -type "string" "map1";
	setAttr -s 39 ".uvst[0].uvsp[0:38]" -type "float2" 0.375 0 0.625 0 0.375
		 0.25 0.625 0.25 0.375 0.5 0.625 0.5 0.375 0.75 0.625 0.75 0.375 1 0.625 1 0.875 0
		 0.875 0.25 0.125 0 0.125 0.25 0.25 0.25 0.375 0.375 0.25 0 0.375 0.875 0.625 0.875
		 0.75 0 0.625 0.375 0.75 0.25 0.375 0.125 0.25 0.125 0.125 0.125 0.375 0.625 0.625
		 0.625 0.875 0.125 0.75 0.125 0.625 0.125 0.5 0 0.5 1 0.5 0.125 0.5 0.25 0.5 0.375
		 0.5 0.5 0.5 0.625 0.5 0.75 0.5 0.875;
	setAttr ".cuvs" -type "string" "map1";
	setAttr ".dcc" -type "string" "Ambient+Diffuse";
	setAttr ".covm[0]"  0 1 1;
	setAttr ".cdvm[0]"  0 1 1;
	setAttr -s 26 ".vt[0:25]"  -0.5 -0.5 0.5 0.5 -0.5 0.5 -0.5 0.5 0.5 0.5 0.5 0.5
		 -0.5 0.5 -0.5 0.5 0.5 -0.5 -0.5 -0.5 -0.5 0.5 -0.5 -0.5 -0.5 0.5 0 -0.5 -0.5 0 0.5 -0.5 0
		 0.5 0.5 0 -0.5 0 0.5 -0.5 0 0 -0.5 0 -0.5 0.5 0 -0.5 0.5 0 0 0.5 0 0.5 0 -0.5 0.5
		 0 0 0.5 0 0.5 0.5 0 0.5 0 0 0.5 -0.5 0 0 -0.5 0 -0.5 -0.5 0 -0.5 0;
	setAttr -s 48 ".ed[0:47]"  0 18 0 2 20 0 4 22 0 6 24 0 0 12 0 1 17 0
		 2 8 0 3 11 0 4 14 0 5 15 0 6 9 0 7 10 0 8 4 0 9 0 0 10 1 0 11 5 0 8 13 1 9 25 1 10 16 1
		 11 21 1 12 2 0 13 9 1 14 6 0 15 7 0 16 11 1 17 3 0 12 13 1 13 14 1 14 23 1 15 16 1
		 16 17 1 17 19 1 18 1 0 19 12 1 20 3 0 21 8 1 22 5 0 23 15 1 24 7 0 25 10 1 18 19 1
		 19 20 1 20 21 1 21 22 1 22 23 1 23 24 1 24 25 1 25 18 1;
	setAttr -s 24 -ch 96 ".fc[0:23]" -type "polyFaces" 
		f 4 0 40 33 -5
		mu 0 4 0 30 32 22
		f 4 1 42 35 -7
		mu 0 4 2 33 34 15
		f 4 28 45 -4 -23
		mu 0 4 25 36 37 6
		f 4 17 47 -1 -14
		mu 0 4 17 38 31 8
		f 4 -15 18 30 -6
		mu 0 4 1 19 28 29
		f 4 26 21 13 4
		mu 0 4 22 23 16 0
		f 4 10 -22 27 22
		mu 0 4 12 16 23 24
		f 4 3 46 -18 -11
		mu 0 4 6 37 38 17
		f 4 29 -19 -12 -24
		mu 0 4 27 28 19 10
		f 4 -36 43 -3 -13
		mu 0 4 15 34 35 4
		f 4 16 -27 20 6
		mu 0 4 14 23 22 2
		f 4 -28 -17 12 8
		mu 0 4 24 23 14 13
		f 4 2 44 -29 -9
		mu 0 4 4 35 36 25
		f 4 -25 -30 -10 -16
		mu 0 4 21 28 27 11
		f 4 -31 24 -8 -26
		mu 0 4 29 28 21 3
		f 4 -34 41 -2 -21
		mu 0 4 22 32 33 2
		f 4 -41 32 5 31
		mu 0 4 32 30 1 29
		f 4 -42 -32 25 -35
		mu 0 4 33 32 29 3
		f 4 -43 34 7 19
		mu 0 4 34 33 3 20
		f 4 -44 -20 15 -37
		mu 0 4 35 34 20 5
		f 4 -45 36 9 -38
		mu 0 4 36 35 5 26
		f 4 -46 37 23 -39
		mu 0 4 37 36 26 7
		f 4 -47 38 11 -40
		mu 0 4 38 37 7 18
		f 4 -48 39 14 -33
		mu 0 4 31 38 18 9;
	setAttr ".cd" -type "dataPolyComponent" Index_Data Edge 0 ;
	setAttr ".cvd" -type "dataPolyComponent" Index_Data Vertex 0 ;
	setAttr ".pd[0]" -type "dataPolyComponent" Index_Data UV 0 ;
	setAttr ".hfd" -type "dataPolyComponent" Index_Data Face 0 ;
createNode mesh -n "BlendshapeBaseShape5Orig" -p "BlendshapeBase";
	rename -uid "F97F606B-4460-9102-4985-22BD6C0ED01A";
	setAttr -k off ".v";
	setAttr ".io" yes;
	setAttr ".vir" yes;
	setAttr ".vif" yes;
	setAttr -s 6 ".gtag";
	setAttr ".gtag[0].gtagnm" -type "string" "back";
	setAttr ".gtag[0].gtagcmp" -type "componentList" 3 "f[2]" "f[12]" "f[20:21]";
	setAttr ".gtag[1].gtagnm" -type "string" "bottom";
	setAttr ".gtag[1].gtagcmp" -type "componentList" 3 "f[3]" "f[7]" "f[22:23]";
	setAttr ".gtag[2].gtagnm" -type "string" "front";
	setAttr ".gtag[2].gtagcmp" -type "componentList" 2 "f[0]" "f[15:17]";
	setAttr ".gtag[3].gtagnm" -type "string" "left";
	setAttr ".gtag[3].gtagcmp" -type "componentList" 2 "f[5:6]" "f[10:11]";
	setAttr ".gtag[4].gtagnm" -type "string" "right";
	setAttr ".gtag[4].gtagcmp" -type "componentList" 3 "f[4]" "f[8]" "f[13:14]";
	setAttr ".gtag[5].gtagnm" -type "string" "top";
	setAttr ".gtag[5].gtagcmp" -type "componentList" 3 "f[1]" "f[9]" "f[18:19]";
	setAttr ".uvst[0].uvsn" -type "string" "map1";
	setAttr -s 39 ".uvst[0].uvsp[0:38]" -type "float2" 0.375 0 0.625 0 0.375
		 0.25 0.625 0.25 0.375 0.5 0.625 0.5 0.375 0.75 0.625 0.75 0.375 1 0.625 1 0.875 0
		 0.875 0.25 0.125 0 0.125 0.25 0.25 0.25 0.375 0.375 0.25 0 0.375 0.875 0.625 0.875
		 0.75 0 0.625 0.375 0.75 0.25 0.375 0.125 0.25 0.125 0.125 0.125 0.375 0.625 0.625
		 0.625 0.875 0.125 0.75 0.125 0.625 0.125 0.5 0 0.5 1 0.5 0.125 0.5 0.25 0.5 0.375
		 0.5 0.5 0.5 0.625 0.5 0.75 0.5 0.875;
	setAttr ".cuvs" -type "string" "map1";
	setAttr ".dcc" -type "string" "Ambient+Diffuse";
	setAttr ".covm[0]"  0 1 1;
	setAttr ".cdvm[0]"  0 1 1;
	setAttr -s 26 ".vt[0:25]"  -0.5 -0.5 0.5 0.5 -0.5 0.5 -0.5 0.5 0.5 0.5 0.5 0.5
		 -0.5 0.5 -0.5 0.5 0.5 -0.5 -0.5 -0.5 -0.5 0.5 -0.5 -0.5 -0.5 0.5 0 -0.5 -0.5 0 0.5 -0.5 0
		 0.5 0.5 0 -0.5 0 0.5 -0.5 0 0 -0.5 0 -0.5 0.5 0 -0.5 0.5 0 0 0.5 0 0.5 0 -0.5 0.5
		 0 0 0.5 0 0.5 0.5 0 0.5 0 0 0.5 -0.5 0 0 -0.5 0 -0.5 -0.5 0 -0.5 0;
	setAttr -s 48 ".ed[0:47]"  0 18 0 2 20 0 4 22 0 6 24 0 0 12 0 1 17 0
		 2 8 0 3 11 0 4 14 0 5 15 0 6 9 0 7 10 0 8 4 0 9 0 0 10 1 0 11 5 0 8 13 1 9 25 1 10 16 1
		 11 21 1 12 2 0 13 9 1 14 6 0 15 7 0 16 11 1 17 3 0 12 13 1 13 14 1 14 23 1 15 16 1
		 16 17 1 17 19 1 18 1 0 19 12 1 20 3 0 21 8 1 22 5 0 23 15 1 24 7 0 25 10 1 18 19 1
		 19 20 1 20 21 1 21 22 1 22 23 1 23 24 1 24 25 1 25 18 1;
	setAttr -s 24 -ch 96 ".fc[0:23]" -type "polyFaces" 
		f 4 0 40 33 -5
		mu 0 4 0 30 32 22
		f 4 1 42 35 -7
		mu 0 4 2 33 34 15
		f 4 28 45 -4 -23
		mu 0 4 25 36 37 6
		f 4 17 47 -1 -14
		mu 0 4 17 38 31 8
		f 4 -15 18 30 -6
		mu 0 4 1 19 28 29
		f 4 26 21 13 4
		mu 0 4 22 23 16 0
		f 4 10 -22 27 22
		mu 0 4 12 16 23 24
		f 4 3 46 -18 -11
		mu 0 4 6 37 38 17
		f 4 29 -19 -12 -24
		mu 0 4 27 28 19 10
		f 4 -36 43 -3 -13
		mu 0 4 15 34 35 4
		f 4 16 -27 20 6
		mu 0 4 14 23 22 2
		f 4 -28 -17 12 8
		mu 0 4 24 23 14 13
		f 4 2 44 -29 -9
		mu 0 4 4 35 36 25
		f 4 -25 -30 -10 -16
		mu 0 4 21 28 27 11
		f 4 -31 24 -8 -26
		mu 0 4 29 28 21 3
		f 4 -34 41 -2 -21
		mu 0 4 22 32 33 2
		f 4 -41 32 5 31
		mu 0 4 32 30 1 29
		f 4 -42 -32 25 -35
		mu 0 4 33 32 29 3
		f 4 -43 34 7 19
		mu 0 4 34 33 3 20
		f 4 -44 -20 15 -37
		mu 0 4 35 34 20 5
		f 4 -45 36 9 -38
		mu 0 4 36 35 5 26
		f 4 -46 37 23 -39
		mu 0 4 37 36 26 7
		f 4 -47 38 11 -40
		mu 0 4 38 37 7 18
		f 4 -48 39 14 -33
		mu 0 4 31 38 18 9;
	setAttr ".cd" -type "dataPolyComponent" Index_Data Edge 0 ;
	setAttr ".cvd" -type "dataPolyComponent" Index_Data Vertex 0 ;
	setAttr ".pd[0]" -type "dataPolyComponent" Index_Data UV 0 ;
	setAttr ".hfd" -type "dataPolyComponent" Index_Data Face 0 ;
createNode joint -n "BlendshapeCtrl" -p "Blendshape_model";
	rename -uid "436A5633-4543-21CA-2B42-41AA5D83DE8C";
	addAttr -ci true -sn "Blendshape" -ln "Blendshape" -min 0 -max 1 -at "double";
	setAttr ".t" -type "double3" 0 1.57006401162919 1 ;
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
	setAttr ".opm" -type "matrix" 1 0 0 0 0 1 0 0 0 0 1 0 0 0 -6 1;
	setAttr ".ds" 2;
	setAttr -k on ".Blendshape";
createNode nurbsCurve -n "center_CTRL2Shape" -p "BlendshapeCtrl";
	rename -uid "22D0C509-434D-26B4-9040-11A9FF21954D";
	setAttr -k off ".v";
	setAttr ".cc" -type "nurbsCurve" 
		3 8 2 no 3
		13 -2 -1 0 1 2 3 4 5 6 7 8 9 10
		11
		0.78361162489122449 4.7982373409884731e-17 -0.78361162489122593
		6.7857323231109122e-17 6.7857323231109122e-17 -1.108194187554389
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122593
		-1.1081941875543881 3.5177356190060272e-33 -1.3322676295501878e-15
		-0.78361162489122449 -4.7982373409884725e-17 0.78361162489122371
		-1.1100856969603225e-16 -6.7857323231109171e-17 1.1081941875543873
		0.78361162489122449 -4.7982373409884719e-17 0.78361162489122371
		1.1081941875543881 -9.2536792101100989e-33 -1.3322676295501878e-15
		0.78361162489122449 4.7982373409884731e-17 -0.78361162489122593
		6.7857323231109122e-17 6.7857323231109122e-17 -1.108194187554389
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122593
		;
createNode transform -n "Spline_BindJoint_model";
	rename -uid "2793A016-4E7E-3119-2AA7-5A961A8327CC";
	setAttr ".rp" -type "double3" 0 0 8 ;
	setAttr ".sp" -type "double3" 0 0 8 ;
createNode joint -n "basebindsplinejoint" -p "Spline_BindJoint_model";
	rename -uid "F5560082-489F-B4E8-0F18-CF9D95B94E52";
	setAttr ".t" -type "double3" 0 3.9999999999999858 7.9999999999999734 ;
	setAttr ".r" -type "double3" 0.024622713887581318 0.49256513654971873 0.98653926473362075 ;
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
createNode joint -n "basebindsplinejoint1" -p "basebindsplinejoint";
	rename -uid "48581900-497F-7975-F9B1-4698E5D498B0";
	setAttr ".t" -type "double3" -0.049082399999999998 -0.98183 0 ;
	setAttr ".r" -type "double3" -0.0048537526768625125 0.11608313394984776 1.2367555685092504 ;
	setAttr ".s" -type "double3" 1.0000643730163574 1.0000643730163574 1 ;
createNode joint -n "basebindsplinejoint2" -p "basebindsplinejoint1";
	rename -uid "8F1AEF84-4E92-0503-588F-95B941DBD9BE";
	setAttr ".t" -type "double3" -0.050899027882084336 -1.0181699999999996 0 ;
	setAttr ".r" -type "double3" 0.05955839204823709 -1.4676662952172896 -4.4251664103950912 ;
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
createNode joint -n "basebindsplinejoint3" -p "basebindsplinejoint2";
	rename -uid "5E135409-45C3-C517-DCB2-9EAEDD04B931";
	setAttr ".t" -type "double3" 0.052254427882084335 -1.0452820000000005 0 ;
	setAttr ".r" -type "double3" -0.0073648347524165204 0.51914865216998185 1.2364772957268058 ;
createNode joint -n "basebindsplinejoint4" -p "basebindsplinejoint3";
	rename -uid "7E214E9C-4D11-DB5E-20A0-619B1A20793F";
	setAttr ".t" -type "double3" 0.047726999999999832 -0.95471799999999951 0 ;
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
createNode ikEffector -n "effector2" -p "basebindsplinejoint3";
	rename -uid "C86DE0E1-4CBE-BF40-DA64-9AB4DB13E2E9";
	setAttr ".v" no;
	setAttr ".hd" yes;
createNode transform -n "splinecurve" -p "Spline_BindJoint_model";
	rename -uid "3BEE25D9-47CE-9C3D-E958-32B9B5865DB8";
	setAttr -l on ".tx";
	setAttr -l on ".ty";
	setAttr -l on ".tz";
	setAttr -l on ".rx";
	setAttr -l on ".ry";
	setAttr -l on ".rz";
	setAttr -l on ".sx";
	setAttr -l on ".sy";
	setAttr -l on ".sz";
createNode nurbsCurve -n "splinecurveShape" -p "splinecurve";
	rename -uid "B9241709-4EE2-71E5-EBEE-7999175C76D5";
	setAttr -k off ".v";
	setAttr ".tw" yes;
createNode nurbsCurve -n "splinecurveShape1Orig" -p "splinecurve";
	rename -uid "93529DA1-4411-0CD3-5A3D-64A60D682083";
	setAttr -k off ".v";
	setAttr ".io" yes;
	setAttr ".cc" -type "nurbsCurve" 
		3 1 0 no 3
		6 0 0 0 4.0049950241773544 4.0049950241773544 4.0049950241773544
		4
		0 3.9999999999999858 7.9999999999999734
		-0.058037909321213638 2.6515172613195541 7.9999999999999742
		-0.058054070999545182 1.3484859145011507 7.9999999999998979
		-1.7347234759768071e-16 4.4018608203399031e-16 8.0000000000000071
		;
createNode ikHandle -n "ikHandle2" -p "Spline_BindJoint_model";
	rename -uid "B56949E2-4FC3-F741-6E2D-ACA40793EA00";
	setAttr ".t" -type "double3" 0.00017517834065428756 -0.0040690604609376901 8.0000000000000071 ;
	setAttr ".r" -type "double3" 0.017031409819282986 -0.34070962620197781 -0.96474142504179117 ;
	setAttr ".roc" yes;
	setAttr ".dwut" 2;
	setAttr ".dpa" 3;
	setAttr ".dwua" 4;
	setAttr ".dtce" yes;
createNode joint -n "Splinectrls" -p "Spline_BindJoint_model";
	rename -uid "B64A7AF5-4EE0-6716-B974-AF9C717502B5";
	addAttr -ci true -sn "liw" -ln "lockInfluenceWeights" -min 0 -max 1 -at "bool";
	setAttr ".t" -type "double3" 0 4 14 ;
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
	setAttr ".opm" -type "matrix" 1 0 0 0 0 1 0 0 0 0 1 0 0 0 -6 1;
	setAttr ".bps" -type "matrix" 1 0 0 0 0 1 0 0 0 0 1 0 0 4 8 1;
	setAttr ".ds" 2;
createNode nurbsCurve -n "center_CTRL2Shape" -p "Splinectrls";
	rename -uid "790359C2-424B-B2BA-2ECA-20A4A76D0081";
	setAttr -k off ".v";
	setAttr ".cc" -type "nurbsCurve" 
		3 8 2 no 3
		13 -2 -1 0 1 2 3 4 5 6 7 8 9 10
		11
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		-1.1081941875543881 3.5177356190060272e-33 -5.7448982375248304e-17
		-0.78361162489122449 -4.7982373409884725e-17 0.78361162489122449
		-1.1100856969603225e-16 -6.7857323231109171e-17 1.1081941875543884
		0.78361162489122449 -4.7982373409884719e-17 0.78361162489122438
		1.1081941875543881 -9.2536792101100989e-33 1.511240500779959e-16
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		;
createNode joint -n "Splinectrls1" -p "Spline_BindJoint_model";
	rename -uid "E3A9824A-451C-CA1C-FBF3-E3BFA4D01B46";
	addAttr -ci true -sn "liw" -ln "lockInfluenceWeights" -min 0 -max 1 -at "bool";
	setAttr ".uoc" 1;
	setAttr ".t" -type "double3" 0.00016410938405897468 -0.0038119496311992407 14 ;
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
	setAttr ".opm" -type "matrix" 1 0 0 0 0 1 0 0 0 0 1 0 0 0 -6 1;
	setAttr ".bps" -type "matrix" 1 0 0 0 0 1 0 0 0 0 1 0 0.00016410938405897468 -0.0038119496311992407 8 1;
	setAttr ".ds" 2;
createNode nurbsCurve -n "center_CTRL2Shape" -p "Splinectrls1";
	rename -uid "70BD4BE4-406B-FC88-CF4A-90A47C6E305C";
	setAttr -k off ".v";
	setAttr ".cc" -type "nurbsCurve" 
		3 8 2 no 3
		13 -2 -1 0 1 2 3 4 5 6 7 8 9 10
		11
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		-1.1081941875543881 3.5177356190060272e-33 -5.7448982375248304e-17
		-0.78361162489122449 -4.7982373409884725e-17 0.78361162489122449
		-1.1100856969603225e-16 -6.7857323231109171e-17 1.1081941875543884
		0.78361162489122449 -4.7982373409884719e-17 0.78361162489122438
		1.1081941875543881 -9.2536792101100989e-33 1.511240500779959e-16
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		;
createNode joint -n "Splinectrls2" -p "Spline_BindJoint_model";
	rename -uid "EBC5FE4D-4D18-3C00-E8F8-088555082416";
	addAttr -ci true -sn "liw" -ln "lockInfluenceWeights" -min 0 -max 1 -at "bool";
	setAttr ".t" -type "double3" 0 1.9980922937393188 14 ;
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
	setAttr ".opm" -type "matrix" 1 0 0 0 0 1 0 0 0 0 1 0 0 0 -6 1;
	setAttr ".bps" -type "matrix" 1 0 0 0 0 1 0 0 0 0 1 0 0 1.9980922937393188 8 1;
	setAttr ".ds" 2;
createNode nurbsCurve -n "center_CTRL2Shape" -p "Splinectrls2";
	rename -uid "DED20F1C-468D-AC0A-8BAD-D2814F1B71B0";
	setAttr -k off ".v";
	setAttr ".cc" -type "nurbsCurve" 
		3 8 2 no 3
		13 -2 -1 0 1 2 3 4 5 6 7 8 9 10
		11
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		-1.1081941875543881 3.5177356190060272e-33 -5.7448982375248304e-17
		-0.78361162489122449 -4.7982373409884725e-17 0.78361162489122449
		-1.1100856969603225e-16 -6.7857323231109171e-17 1.1081941875543884
		0.78361162489122449 -4.7982373409884719e-17 0.78361162489122438
		1.1081941875543881 -9.2536792101100989e-33 1.511240500779959e-16
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		;
createNode transform -n "Zerogroup";
	rename -uid "F150B1AE-4239-2754-797D-199838D2D720";
	setAttr ".t" -type "double3" 0 0 -8 ;
createNode joint -n "basezerojoint1" -p "Zerogroup";
	rename -uid "E0E99F67-4870-23DB-789A-58A9E9950C9C";
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
createNode nurbsCurve -n "center_CTRL2Shape" -p "basezerojoint1";
	rename -uid "B16E3BCC-499E-14FE-341B-8892EC3CD265";
	setAttr -k off ".v";
	setAttr ".cc" -type "nurbsCurve" 
		3 8 2 no 3
		13 -2 -1 0 1 2 3 4 5 6 7 8 9 10
		11
		0.78361162489122482 4.7982373409878883e-17 -0.7836116248912246
		2.2204460492503131e-16 6.7857323231099298e-17 -1.1081941875543873
		-0.78361162489122416 4.7982373409872572e-17 -0.7836116248912246
		-1.1081941875543877 -1.2621774483536189e-29 0
		-0.78361162489122416 -4.7982373409897815e-17 0.7836116248912246
		2.2204460492503131e-16 -6.7857323231124542e-17 1.1081941875543881
		0.78361162489122482 -4.7982373409891505e-17 0.7836116248912246
		1.1081941875543881 -6.3108872417680944e-30 0
		0.78361162489122482 4.7982373409878883e-17 -0.7836116248912246
		2.2204460492503131e-16 6.7857323231099298e-17 -1.1081941875543873
		-0.78361162489122416 4.7982373409872572e-17 -0.7836116248912246
		;
createNode transform -n "Zerogroup1" -p "basezerojoint1";
	rename -uid "C6F4D6CA-4507-26CA-83C8-6899C26FEF1F";
	setAttr ".t" -type "double3" 0 2 6 ;
	setAttr ".rp" -type "double3" 0 0 -6 ;
	setAttr ".sp" -type "double3" 0 0 -6 ;
createNode joint -n "basezerojoint2" -p "Zerogroup1";
	rename -uid "6DD1126D-4CD5-9250-14CB-F2B4972AF921";
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
	setAttr ".opm" -type "matrix" 1 0 0 0 0 1 0 0 0 0 1 0 0 0 -6 1;
createNode nurbsCurve -n "center_CTRL2Shape" -p "basezerojoint2";
	rename -uid "7B2B814C-40A6-A3A0-DDEF-8C840E8D1CD4";
	setAttr -k off ".v";
	setAttr ".cc" -type "nurbsCurve" 
		3 8 2 no 3
		13 -2 -1 0 1 2 3 4 5 6 7 8 9 10
		11
		0.78361162489122482 0 -0.78361162489122549
		2.2204460492503131e-16 0 -1.1081941875543873
		-0.78361162489122416 0 -0.78361162489122549
		-1.1081941875543877 0 0
		-0.78361162489122416 0 0.78361162489122549
		2.2204460492503131e-16 0 1.108194187554389
		0.78361162489122482 0 0.78361162489122549
		1.1081941875543881 0 0
		0.78361162489122482 0 -0.78361162489122549
		2.2204460492503131e-16 0 -1.1081941875543873
		-0.78361162489122416 0 -0.78361162489122549
		;
createNode transform -n "Zerogroup2" -p "basezerojoint2";
	rename -uid "2A881B50-4019-5BE4-1267-F09228893BDD";
	setAttr ".t" -type "double3" -3 0 0 ;
createNode joint -n "basezerojoint3" -p "Zerogroup2";
	rename -uid "612B6DAF-41E2-E4BD-CEE4-8D985D38435B";
	addAttr -ci true -sn "space" -ln "space" -min 0 -max 1 -en "world:neck" -at "enum";
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
	setAttr -k on ".space" 1;
createNode nurbsCurve -n "center_CTRL2Shape" -p "basezerojoint3";
	rename -uid "B6C975B1-4710-5700-EC49-11B501919815";
	setAttr -k off ".v";
	setAttr ".cc" -type "nurbsCurve" 
		3 8 2 no 3
		13 -2 -1 0 1 2 3 4 5 6 7 8 9 10
		11
		0.7836116248912246 0 -0.78361162489122549
		0 0 -1.108194187554389
		-0.78361162489122416 0 -0.78361162489122549
		-1.1081941875543873 0 0
		-0.78361162489122416 0 0.78361162489122549
		0 0 1.108194187554389
		0.7836116248912246 0 0.78361162489122549
		1.1081941875543881 0 0
		0.7836116248912246 0 -0.78361162489122549
		0 0 -1.108194187554389
		-0.78361162489122416 0 -0.78361162489122549
		;
createNode transform -n "group1";
	rename -uid "CC3255C0-43B9-FE14-29D5-20AD050B0D1A";
	setAttr ".t" -type "double3" 0 0 11 ;
createNode joint -n "Driverbasejoint" -p "group1";
	rename -uid "C2F61D59-4438-A0AF-759A-F4813CC4D962";
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
createNode nurbsCurve -n "center_CTRL2Shape" -p "Driverbasejoint";
	rename -uid "09FB5D16-4DAE-286D-47CE-1FA6FF787F72";
	setAttr -k off ".v";
	setAttr ".cc" -type "nurbsCurve" 
		3 8 2 no 3
		13 -2 -1 0 1 2 3 4 5 6 7 8 9 10
		11
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		-1.1081941875543881 3.5177356190060272e-33 -5.7448982375248304e-17
		-0.78361162489122449 -4.7982373409884725e-17 0.78361162489122449
		-1.1100856969603225e-16 -6.7857323231109171e-17 1.1081941875543884
		0.78361162489122449 -4.7982373409884719e-17 0.78361162489122438
		1.1081941875543881 -9.2536792101100989e-33 1.511240500779959e-16
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		;
createNode transform -n "group2" -p "Driverbasejoint";
	rename -uid "529055D3-42B6-01BB-F59F-BAB190ACD211";
	setAttr ".t" -type "double3" 0 2 0 ;
createNode joint -n "Drivenbasejoint" -p "group2";
	rename -uid "3D9926F0-4C1A-394D-F114-949E5E5C0502";
	setAttr ".mnrl" -type "double3" -360 -360 -360 ;
	setAttr ".mxrl" -type "double3" 360 360 360 ;
createNode nurbsCurve -n "center_CTRL2Shape" -p "Drivenbasejoint";
	rename -uid "2B1DF24C-4DBA-71DA-6F20-29917216DB46";
	setAttr -k off ".v";
	setAttr ".cc" -type "nurbsCurve" 
		3 8 2 no 3
		13 -2 -1 0 1 2 3 4 5 6 7 8 9 10
		11
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		-1.1081941875543881 3.5177356190060272e-33 -5.7448982375248304e-17
		-0.78361162489122449 -4.7982373409884725e-17 0.78361162489122449
		-1.1100856969603225e-16 -6.7857323231109171e-17 1.1081941875543884
		0.78361162489122449 -4.7982373409884719e-17 0.78361162489122438
		1.1081941875543881 -9.2536792101100989e-33 1.511240500779959e-16
		0.78361162489122449 4.7982373409884731e-17 -0.7836116248912246
		6.7857323231109122e-17 6.7857323231109122e-17 -1.1081941875543877
		-0.78361162489122449 4.7982373409884719e-17 -0.78361162489122438
		;
createNode lightLinker -s -n "lightLinker1";
	rename -uid "FD23FC73-43AA-56CC-FDEF-51B22BCF6683";
	setAttr -s 2 ".lnk";
	setAttr -s 2 ".slnk";
createNode shapeEditorManager -n "shapeEditorManager";
	rename -uid "5EDDE81C-4C31-7FFE-34AA-3BBD24AD5FCA";
	setAttr ".bsdt[0].bscd" -type "Int32Array" 1 0 ;
createNode poseInterpolatorManager -n "poseInterpolatorManager";
	rename -uid "B73DBA67-4A3C-BEDA-888C-2699B423B56E";
createNode displayLayerManager -n "layerManager";
	rename -uid "9A55811D-45B1-2E7F-B0FD-A28D8715CE54";
createNode displayLayer -n "defaultLayer";
	rename -uid "4F7212AA-44C1-6C92-C521-78BD1D6B400F";
	setAttr ".ufem" -type "stringArray" 0  ;
createNode renderLayerManager -n "renderLayerManager";
	rename -uid "64F96CB8-4132-6742-8F0B-9FB87D516326";
createNode renderLayer -n "defaultRenderLayer";
	rename -uid "A09911BC-4762-0999-0A25-DBB3A9C06940";
	setAttr ".g" yes;
createNode aiOptions -s -n "defaultArnoldRenderOptions";
	rename -uid "119DD9CF-434D-3F27-6BAF-118981601403";
	setAttr ".version" -type "string" "5.5.0";
createNode aiAOVFilter -s -n "defaultArnoldFilter";
	rename -uid "5D247ACD-429C-C63D-81EC-97A706D22A9A";
	setAttr ".ai_translator" -type "string" "gaussian";
createNode aiAOVDriver -s -n "defaultArnoldDriver";
	rename -uid "44A110CB-4819-CB76-6513-9BB7F9434946";
	setAttr ".ai_translator" -type "string" "exr";
createNode aiAOVDriver -s -n "defaultArnoldDisplayDriver";
	rename -uid "382DFB84-430E-8DCF-77AB-76B38D23CCC2";
	setAttr ".ai_translator" -type "string" "maya";
	setAttr ".output_mode" 0;
createNode aiImagerDenoiserOidn -s -n "defaultArnoldDenoiser";
	rename -uid "1702F060-482B-47DD-5113-A28B6F4F3CDB";
createNode ikRPsolver -n "ikRPsolver";
	rename -uid "6D3CEDB6-4540-6253-A4A0-2FB89BC6C439";
createNode script -n "uiConfigurationScriptNode";
	rename -uid "EBE41B39-45D4-DBD9-EC62-FB91CF18DEEE";
	setAttr ".b" -type "string" (
		"// Maya Mel UI Configuration File.\n//\n//  This script is machine generated.  Edit at your own risk.\n//\n//\n\nglobal string $gMainPane;\nif (`paneLayout -exists $gMainPane`) {\n\n\tglobal int $gUseScenePanelConfig;\n\tint    $useSceneConfig = $gUseScenePanelConfig;\n\tint    $nodeEditorPanelVisible = stringArrayContains(\"nodeEditorPanel1\", `getPanel -vis`);\n\tint    $nodeEditorWorkspaceControlOpen = (`workspaceControl -exists nodeEditorPanel1Window` && `workspaceControl -q -visible nodeEditorPanel1Window`);\n\tint    $menusOkayInPanels = `optionVar -q allowMenusInPanels`;\n\tint    $nVisPanes = `paneLayout -q -nvp $gMainPane`;\n\tint    $nPanes = 0;\n\tstring $editorName;\n\tstring $panelName;\n\tstring $itemFilterName;\n\tstring $panelConfig;\n\n\t//\n\t//  get current state of the UI\n\t//\n\tsceneUIReplacement -update $gMainPane;\n\n\t$panelName = `sceneUIReplacement -getNextPanel \"modelPanel\" (localizedPanelLabel(\"Top View\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tmodelPanel -edit -l (localizedPanelLabel(\"Top View\")) -mbv $menusOkayInPanels  $panelName;\n"
		+ "\t\t$editorName = $panelName;\n        modelEditor -e \n            -camera \"|top\" \n            -useInteractiveMode 0\n            -displayLights \"default\" \n            -displayAppearance \"smoothShaded\" \n            -activeOnly 0\n            -ignorePanZoom 0\n            -wireframeOnShaded 0\n            -headsUpDisplay 1\n            -holdOuts 1\n            -selectionHiliteDisplay 1\n            -useDefaultMaterial 0\n            -bufferMode \"double\" \n            -twoSidedLighting 0\n            -backfaceCulling 0\n            -xray 0\n            -jointXray 0\n            -activeComponentsXray 0\n            -displayTextures 0\n            -smoothWireframe 0\n            -lineWidth 1\n            -textureAnisotropic 0\n            -textureHilight 1\n            -textureSampling 2\n            -textureDisplay \"modulate\" \n            -textureMaxSize 32768\n            -fogging 0\n            -fogSource \"fragment\" \n            -fogMode \"linear\" \n            -fogStart 0\n            -fogEnd 100\n            -fogDensity 0.1\n            -fogColor 0.5 0.5 0.5 1 \n"
		+ "            -depthOfFieldPreview 1\n            -maxConstantTransparency 1\n            -rendererName \"vp2Renderer\" \n            -objectFilterShowInHUD 1\n            -isFiltered 0\n            -colorResolution 256 256 \n            -bumpResolution 512 512 \n            -textureCompression 0\n            -transparencyAlgorithm \"frontAndBackCull\" \n            -transpInShadows 0\n            -cullingOverride \"none\" \n            -lowQualityLighting 0\n            -maximumNumHardwareLights 1\n            -occlusionCulling 0\n            -shadingModel 0\n            -useBaseRenderer 0\n            -useReducedRenderer 0\n            -smallObjectCulling 0\n            -smallObjectThreshold -1 \n            -interactiveDisableShadows 0\n            -interactiveBackFaceCull 0\n            -sortTransparent 1\n            -controllers 1\n            -nurbsCurves 1\n            -nurbsSurfaces 1\n            -polymeshes 1\n            -subdivSurfaces 1\n            -planes 1\n            -lights 1\n            -cameras 1\n            -controlVertices 1\n"
		+ "            -hulls 1\n            -grid 1\n            -imagePlane 1\n            -joints 1\n            -ikHandles 1\n            -deformers 1\n            -dynamics 1\n            -particleInstancers 1\n            -fluids 1\n            -hairSystems 1\n            -follicles 1\n            -nCloths 1\n            -nParticles 1\n            -nRigids 1\n            -dynamicConstraints 1\n            -locators 1\n            -manipulators 1\n            -pluginShapes 1\n            -dimensions 1\n            -handles 1\n            -pivots 1\n            -textures 1\n            -strokes 1\n            -motionTrails 1\n            -clipGhosts 1\n            -bluePencil 1\n            -greasePencils 0\n            -excludeObjectPreset \"All\" \n            -shadows 0\n            -captureSequenceNumber -1\n            -width 1\n            -height 1\n            -sceneRenderFilter 0\n            $editorName;\n        modelEditor -e -viewSelected 0 $editorName;\n        modelEditor -e \n            -pluginObjects \"gpuCacheDisplayFilter\" 1 \n            $editorName;\n"
		+ "\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextPanel \"modelPanel\" (localizedPanelLabel(\"Side View\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tmodelPanel -edit -l (localizedPanelLabel(\"Side View\")) -mbv $menusOkayInPanels  $panelName;\n\t\t$editorName = $panelName;\n        modelEditor -e \n            -camera \"|side\" \n            -useInteractiveMode 0\n            -displayLights \"default\" \n            -displayAppearance \"smoothShaded\" \n            -activeOnly 0\n            -ignorePanZoom 0\n            -wireframeOnShaded 0\n            -headsUpDisplay 1\n            -holdOuts 1\n            -selectionHiliteDisplay 1\n            -useDefaultMaterial 0\n            -bufferMode \"double\" \n            -twoSidedLighting 0\n            -backfaceCulling 0\n            -xray 0\n            -jointXray 0\n            -activeComponentsXray 0\n            -displayTextures 0\n            -smoothWireframe 0\n            -lineWidth 1\n            -textureAnisotropic 0\n"
		+ "            -textureHilight 1\n            -textureSampling 2\n            -textureDisplay \"modulate\" \n            -textureMaxSize 32768\n            -fogging 0\n            -fogSource \"fragment\" \n            -fogMode \"linear\" \n            -fogStart 0\n            -fogEnd 100\n            -fogDensity 0.1\n            -fogColor 0.5 0.5 0.5 1 \n            -depthOfFieldPreview 1\n            -maxConstantTransparency 1\n            -rendererName \"vp2Renderer\" \n            -objectFilterShowInHUD 1\n            -isFiltered 0\n            -colorResolution 256 256 \n            -bumpResolution 512 512 \n            -textureCompression 0\n            -transparencyAlgorithm \"frontAndBackCull\" \n            -transpInShadows 0\n            -cullingOverride \"none\" \n            -lowQualityLighting 0\n            -maximumNumHardwareLights 1\n            -occlusionCulling 0\n            -shadingModel 0\n            -useBaseRenderer 0\n            -useReducedRenderer 0\n            -smallObjectCulling 0\n            -smallObjectThreshold -1 \n            -interactiveDisableShadows 0\n"
		+ "            -interactiveBackFaceCull 0\n            -sortTransparent 1\n            -controllers 1\n            -nurbsCurves 1\n            -nurbsSurfaces 1\n            -polymeshes 1\n            -subdivSurfaces 1\n            -planes 1\n            -lights 1\n            -cameras 1\n            -controlVertices 1\n            -hulls 1\n            -grid 1\n            -imagePlane 1\n            -joints 1\n            -ikHandles 1\n            -deformers 1\n            -dynamics 1\n            -particleInstancers 1\n            -fluids 1\n            -hairSystems 1\n            -follicles 1\n            -nCloths 1\n            -nParticles 1\n            -nRigids 1\n            -dynamicConstraints 1\n            -locators 1\n            -manipulators 1\n            -pluginShapes 1\n            -dimensions 1\n            -handles 1\n            -pivots 1\n            -textures 1\n            -strokes 1\n            -motionTrails 1\n            -clipGhosts 1\n            -bluePencil 1\n            -greasePencils 0\n            -excludeObjectPreset \"All\" \n"
		+ "            -shadows 0\n            -captureSequenceNumber -1\n            -width 1\n            -height 1\n            -sceneRenderFilter 0\n            $editorName;\n        modelEditor -e -viewSelected 0 $editorName;\n        modelEditor -e \n            -pluginObjects \"gpuCacheDisplayFilter\" 1 \n            $editorName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextPanel \"modelPanel\" (localizedPanelLabel(\"Front View\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tmodelPanel -edit -l (localizedPanelLabel(\"Front View\")) -mbv $menusOkayInPanels  $panelName;\n\t\t$editorName = $panelName;\n        modelEditor -e \n            -camera \"|front\" \n            -useInteractiveMode 0\n            -displayLights \"default\" \n            -displayAppearance \"smoothShaded\" \n            -activeOnly 0\n            -ignorePanZoom 0\n            -wireframeOnShaded 0\n            -headsUpDisplay 1\n            -holdOuts 1\n            -selectionHiliteDisplay 1\n"
		+ "            -useDefaultMaterial 0\n            -bufferMode \"double\" \n            -twoSidedLighting 0\n            -backfaceCulling 0\n            -xray 0\n            -jointXray 0\n            -activeComponentsXray 0\n            -displayTextures 0\n            -smoothWireframe 0\n            -lineWidth 1\n            -textureAnisotropic 0\n            -textureHilight 1\n            -textureSampling 2\n            -textureDisplay \"modulate\" \n            -textureMaxSize 32768\n            -fogging 0\n            -fogSource \"fragment\" \n            -fogMode \"linear\" \n            -fogStart 0\n            -fogEnd 100\n            -fogDensity 0.1\n            -fogColor 0.5 0.5 0.5 1 \n            -depthOfFieldPreview 1\n            -maxConstantTransparency 1\n            -rendererName \"vp2Renderer\" \n            -objectFilterShowInHUD 1\n            -isFiltered 0\n            -colorResolution 256 256 \n            -bumpResolution 512 512 \n            -textureCompression 0\n            -transparencyAlgorithm \"frontAndBackCull\" \n            -transpInShadows 0\n"
		+ "            -cullingOverride \"none\" \n            -lowQualityLighting 0\n            -maximumNumHardwareLights 1\n            -occlusionCulling 0\n            -shadingModel 0\n            -useBaseRenderer 0\n            -useReducedRenderer 0\n            -smallObjectCulling 0\n            -smallObjectThreshold -1 \n            -interactiveDisableShadows 0\n            -interactiveBackFaceCull 0\n            -sortTransparent 1\n            -controllers 1\n            -nurbsCurves 1\n            -nurbsSurfaces 1\n            -polymeshes 1\n            -subdivSurfaces 1\n            -planes 1\n            -lights 1\n            -cameras 1\n            -controlVertices 1\n            -hulls 1\n            -grid 1\n            -imagePlane 1\n            -joints 1\n            -ikHandles 1\n            -deformers 1\n            -dynamics 1\n            -particleInstancers 1\n            -fluids 1\n            -hairSystems 1\n            -follicles 1\n            -nCloths 1\n            -nParticles 1\n            -nRigids 1\n            -dynamicConstraints 1\n"
		+ "            -locators 1\n            -manipulators 1\n            -pluginShapes 1\n            -dimensions 1\n            -handles 1\n            -pivots 1\n            -textures 1\n            -strokes 1\n            -motionTrails 1\n            -clipGhosts 1\n            -bluePencil 1\n            -greasePencils 0\n            -excludeObjectPreset \"All\" \n            -shadows 0\n            -captureSequenceNumber -1\n            -width 1\n            -height 1\n            -sceneRenderFilter 0\n            $editorName;\n        modelEditor -e -viewSelected 0 $editorName;\n        modelEditor -e \n            -pluginObjects \"gpuCacheDisplayFilter\" 1 \n            $editorName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextPanel \"modelPanel\" (localizedPanelLabel(\"Persp View\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tmodelPanel -edit -l (localizedPanelLabel(\"Persp View\")) -mbv $menusOkayInPanels  $panelName;\n\t\t$editorName = $panelName;\n        modelEditor -e \n"
		+ "            -camera \"|persp\" \n            -useInteractiveMode 0\n            -displayLights \"default\" \n            -displayAppearance \"smoothShaded\" \n            -activeOnly 0\n            -ignorePanZoom 0\n            -wireframeOnShaded 0\n            -headsUpDisplay 1\n            -holdOuts 1\n            -selectionHiliteDisplay 1\n            -useDefaultMaterial 0\n            -bufferMode \"double\" \n            -twoSidedLighting 0\n            -backfaceCulling 0\n            -xray 0\n            -jointXray 0\n            -activeComponentsXray 0\n            -displayTextures 0\n            -smoothWireframe 0\n            -lineWidth 1\n            -textureAnisotropic 0\n            -textureHilight 1\n            -textureSampling 2\n            -textureDisplay \"modulate\" \n            -textureMaxSize 32768\n            -fogging 0\n            -fogSource \"fragment\" \n            -fogMode \"linear\" \n            -fogStart 0\n            -fogEnd 100\n            -fogDensity 0.1\n            -fogColor 0.5 0.5 0.5 1 \n            -depthOfFieldPreview 1\n"
		+ "            -maxConstantTransparency 1\n            -rendererName \"vp2Renderer\" \n            -objectFilterShowInHUD 1\n            -isFiltered 0\n            -colorResolution 256 256 \n            -bumpResolution 512 512 \n            -textureCompression 0\n            -transparencyAlgorithm \"frontAndBackCull\" \n            -transpInShadows 0\n            -cullingOverride \"none\" \n            -lowQualityLighting 0\n            -maximumNumHardwareLights 1\n            -occlusionCulling 0\n            -shadingModel 0\n            -useBaseRenderer 0\n            -useReducedRenderer 0\n            -smallObjectCulling 0\n            -smallObjectThreshold -1 \n            -interactiveDisableShadows 0\n            -interactiveBackFaceCull 0\n            -sortTransparent 1\n            -controllers 1\n            -nurbsCurves 1\n            -nurbsSurfaces 1\n            -polymeshes 1\n            -subdivSurfaces 1\n            -planes 1\n            -lights 1\n            -cameras 1\n            -controlVertices 1\n            -hulls 1\n            -grid 1\n"
		+ "            -imagePlane 1\n            -joints 1\n            -ikHandles 1\n            -deformers 1\n            -dynamics 1\n            -particleInstancers 1\n            -fluids 1\n            -hairSystems 1\n            -follicles 1\n            -nCloths 1\n            -nParticles 1\n            -nRigids 1\n            -dynamicConstraints 1\n            -locators 1\n            -manipulators 1\n            -pluginShapes 1\n            -dimensions 1\n            -handles 1\n            -pivots 1\n            -textures 1\n            -strokes 1\n            -motionTrails 1\n            -clipGhosts 1\n            -bluePencil 1\n            -greasePencils 0\n            -excludeObjectPreset \"All\" \n            -shadows 0\n            -captureSequenceNumber -1\n            -width 1117\n            -height 706\n            -sceneRenderFilter 0\n            $editorName;\n        modelEditor -e -viewSelected 0 $editorName;\n        modelEditor -e \n            -pluginObjects \"gpuCacheDisplayFilter\" 1 \n            $editorName;\n\t\tif (!$useSceneConfig) {\n"
		+ "\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextPanel \"outlinerPanel\" (localizedPanelLabel(\"ToggledOutliner\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\toutlinerPanel -edit -l (localizedPanelLabel(\"ToggledOutliner\")) -mbv $menusOkayInPanels  $panelName;\n\t\t$editorName = $panelName;\n        outlinerEditor -e \n            -showShapes 0\n            -showAssignedMaterials 0\n            -showTimeEditor 1\n            -showReferenceNodes 1\n            -showReferenceMembers 1\n            -showAttributes 0\n            -showConnected 0\n            -showAnimCurvesOnly 0\n            -showMuteInfo 0\n            -organizeByLayer 1\n            -organizeByClip 1\n            -showAnimLayerWeight 1\n            -autoExpandLayers 1\n            -autoExpand 0\n            -showDagOnly 1\n            -showAssets 1\n            -showContainedOnly 1\n            -showPublishedAsConnected 0\n            -showParentContainers 0\n            -showContainerContents 1\n            -ignoreDagHierarchy 0\n"
		+ "            -expandConnections 0\n            -showUpstreamCurves 1\n            -showUnitlessCurves 1\n            -showCompounds 1\n            -showLeafs 1\n            -showNumericAttrsOnly 0\n            -highlightActive 1\n            -autoSelectNewObjects 0\n            -doNotSelectNewObjects 0\n            -dropIsParent 1\n            -transmitFilters 0\n            -setFilter \"defaultSetFilter\" \n            -showSetMembers 1\n            -allowMultiSelection 1\n            -alwaysToggleSelect 0\n            -directSelect 0\n            -isSet 0\n            -isSetMember 0\n            -showUfeItems 1\n            -displayMode \"DAG\" \n            -expandObjects 0\n            -setsIgnoreFilters 1\n            -containersIgnoreFilters 0\n            -editAttrName 0\n            -showAttrValues 0\n            -highlightSecondary 0\n            -showUVAttrsOnly 0\n            -showTextureNodesOnly 0\n            -attrAlphaOrder \"default\" \n            -animLayerFilterOptions \"allAffecting\" \n            -sortOrder \"none\" \n            -longNames 0\n"
		+ "            -niceNames 1\n            -showNamespace 1\n            -showPinIcons 0\n            -mapMotionTrails 0\n            -ignoreHiddenAttribute 0\n            -ignoreOutlinerColor 0\n            -renderFilterVisible 0\n            -renderFilterIndex 0\n            -selectionOrder \"chronological\" \n            -expandAttribute 0\n            $editorName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextPanel \"outlinerPanel\" (localizedPanelLabel(\"Outliner\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\toutlinerPanel -edit -l (localizedPanelLabel(\"Outliner\")) -mbv $menusOkayInPanels  $panelName;\n\t\t$editorName = $panelName;\n        outlinerEditor -e \n            -showShapes 0\n            -showAssignedMaterials 0\n            -showTimeEditor 1\n            -showReferenceNodes 0\n            -showReferenceMembers 0\n            -showAttributes 0\n            -showConnected 0\n            -showAnimCurvesOnly 0\n            -showMuteInfo 0\n"
		+ "            -organizeByLayer 1\n            -organizeByClip 1\n            -showAnimLayerWeight 1\n            -autoExpandLayers 1\n            -autoExpand 0\n            -showDagOnly 1\n            -showAssets 1\n            -showContainedOnly 1\n            -showPublishedAsConnected 0\n            -showParentContainers 0\n            -showContainerContents 1\n            -ignoreDagHierarchy 0\n            -expandConnections 0\n            -showUpstreamCurves 1\n            -showUnitlessCurves 1\n            -showCompounds 1\n            -showLeafs 1\n            -showNumericAttrsOnly 0\n            -highlightActive 1\n            -autoSelectNewObjects 0\n            -doNotSelectNewObjects 0\n            -dropIsParent 1\n            -transmitFilters 0\n            -setFilter \"defaultSetFilter\" \n            -showSetMembers 1\n            -allowMultiSelection 1\n            -alwaysToggleSelect 0\n            -directSelect 0\n            -showUfeItems 1\n            -displayMode \"DAG\" \n            -expandObjects 0\n            -setsIgnoreFilters 1\n"
		+ "            -containersIgnoreFilters 0\n            -editAttrName 0\n            -showAttrValues 0\n            -highlightSecondary 0\n            -showUVAttrsOnly 0\n            -showTextureNodesOnly 0\n            -attrAlphaOrder \"default\" \n            -animLayerFilterOptions \"allAffecting\" \n            -sortOrder \"none\" \n            -longNames 0\n            -niceNames 1\n            -showNamespace 1\n            -showPinIcons 0\n            -mapMotionTrails 0\n            -ignoreHiddenAttribute 0\n            -ignoreOutlinerColor 0\n            -renderFilterVisible 0\n            $editorName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"graphEditor\" (localizedPanelLabel(\"Graph Editor\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Graph Editor\")) -mbv $menusOkayInPanels  $panelName;\n\n\t\t\t$editorName = ($panelName+\"OutlineEd\");\n            outlinerEditor -e \n                -showShapes 1\n"
		+ "                -showAssignedMaterials 0\n                -showTimeEditor 1\n                -showReferenceNodes 0\n                -showReferenceMembers 0\n                -showAttributes 1\n                -showConnected 1\n                -showAnimCurvesOnly 1\n                -showMuteInfo 0\n                -organizeByLayer 1\n                -organizeByClip 1\n                -showAnimLayerWeight 1\n                -autoExpandLayers 1\n                -autoExpand 1\n                -showDagOnly 0\n                -showAssets 1\n                -showContainedOnly 0\n                -showPublishedAsConnected 0\n                -showParentContainers 0\n                -showContainerContents 0\n                -ignoreDagHierarchy 0\n                -expandConnections 1\n                -showUpstreamCurves 1\n                -showUnitlessCurves 1\n                -showCompounds 0\n                -showLeafs 1\n                -showNumericAttrsOnly 1\n                -highlightActive 0\n                -autoSelectNewObjects 1\n                -doNotSelectNewObjects 0\n"
		+ "                -dropIsParent 1\n                -transmitFilters 1\n                -setFilter \"0\" \n                -showSetMembers 0\n                -allowMultiSelection 1\n                -alwaysToggleSelect 0\n                -directSelect 0\n                -showUfeItems 1\n                -displayMode \"DAG\" \n                -expandObjects 0\n                -setsIgnoreFilters 1\n                -containersIgnoreFilters 0\n                -editAttrName 0\n                -showAttrValues 0\n                -highlightSecondary 0\n                -showUVAttrsOnly 0\n                -showTextureNodesOnly 0\n                -attrAlphaOrder \"default\" \n                -animLayerFilterOptions \"allAffecting\" \n                -sortOrder \"none\" \n                -longNames 0\n                -niceNames 1\n                -showNamespace 1\n                -showPinIcons 1\n                -mapMotionTrails 1\n                -ignoreHiddenAttribute 0\n                -ignoreOutlinerColor 0\n                -renderFilterVisible 0\n                $editorName;\n"
		+ "\n\t\t\t$editorName = ($panelName+\"GraphEd\");\n            animCurveEditor -e \n                -displayValues 0\n                -snapTime \"integer\" \n                -snapValue \"none\" \n                -showPlayRangeShades \"on\" \n                -lockPlayRangeShades \"off\" \n                -smoothness \"fine\" \n                -resultSamples 1\n                -resultScreenSamples 0\n                -resultUpdate \"delayed\" \n                -showUpstreamCurves 1\n                -tangentScale 1\n                -tangentLineThickness 1\n                -keyMinScale 1\n                -stackedCurvesMin -1\n                -stackedCurvesMax 1\n                -stackedCurvesSpace 0.2\n                -preSelectionHighlight 0\n                -limitToSelectedCurves 0\n                -constrainDrag 0\n                -valueLinesToggle 0\n                -highlightAffectedCurves 0\n                $editorName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"dopeSheetPanel\" (localizedPanelLabel(\"Dope Sheet\")) `;\n"
		+ "\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Dope Sheet\")) -mbv $menusOkayInPanels  $panelName;\n\n\t\t\t$editorName = ($panelName+\"OutlineEd\");\n            outlinerEditor -e \n                -showShapes 1\n                -showAssignedMaterials 0\n                -showTimeEditor 1\n                -showReferenceNodes 0\n                -showReferenceMembers 0\n                -showAttributes 1\n                -showConnected 1\n                -showAnimCurvesOnly 1\n                -showMuteInfo 0\n                -organizeByLayer 1\n                -organizeByClip 1\n                -showAnimLayerWeight 1\n                -autoExpandLayers 1\n                -autoExpand 1\n                -showDagOnly 0\n                -showAssets 1\n                -showContainedOnly 0\n                -showPublishedAsConnected 0\n                -showParentContainers 0\n                -showContainerContents 0\n                -ignoreDagHierarchy 0\n                -expandConnections 1\n"
		+ "                -showUpstreamCurves 1\n                -showUnitlessCurves 0\n                -showCompounds 0\n                -showLeafs 1\n                -showNumericAttrsOnly 1\n                -highlightActive 0\n                -autoSelectNewObjects 0\n                -doNotSelectNewObjects 1\n                -dropIsParent 1\n                -transmitFilters 0\n                -setFilter \"0\" \n                -showSetMembers 1\n                -allowMultiSelection 1\n                -alwaysToggleSelect 0\n                -directSelect 0\n                -showUfeItems 1\n                -displayMode \"DAG\" \n                -expandObjects 0\n                -setsIgnoreFilters 1\n                -containersIgnoreFilters 0\n                -editAttrName 0\n                -showAttrValues 0\n                -highlightSecondary 0\n                -showUVAttrsOnly 0\n                -showTextureNodesOnly 0\n                -attrAlphaOrder \"default\" \n                -animLayerFilterOptions \"allAffecting\" \n                -sortOrder \"none\" \n"
		+ "                -longNames 0\n                -niceNames 1\n                -showNamespace 1\n                -showPinIcons 0\n                -mapMotionTrails 1\n                -ignoreHiddenAttribute 0\n                -ignoreOutlinerColor 0\n                -renderFilterVisible 0\n                $editorName;\n\n\t\t\t$editorName = ($panelName+\"DopeSheetEd\");\n            dopeSheetEditor -e \n                -displayValues 0\n                -snapTime \"none\" \n                -snapValue \"none\" \n                -outliner \"dopeSheetPanel1OutlineEd\" \n                -hierarchyBelow 0\n                -selectionWindow 0 0 0 0 \n                $editorName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"timeEditorPanel\" (localizedPanelLabel(\"Time Editor\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Time Editor\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n"
		+ "\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"clipEditorPanel\" (localizedPanelLabel(\"Trax Editor\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Trax Editor\")) -mbv $menusOkayInPanels  $panelName;\n\n\t\t\t$editorName = clipEditorNameFromPanel($panelName);\n            clipEditor -e \n                -displayValues 0\n                -snapTime \"none\" \n                -snapValue \"none\" \n                -initialized 0\n                -manageSequencer 0 \n                $editorName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"sequenceEditorPanel\" (localizedPanelLabel(\"Camera Sequencer\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Camera Sequencer\")) -mbv $menusOkayInPanels  $panelName;\n\n\t\t\t$editorName = sequenceEditorNameFromPanel($panelName);\n            clipEditor -e \n                -displayValues 0\n"
		+ "                -snapTime \"none\" \n                -snapValue \"none\" \n                -initialized 0\n                -manageSequencer 1 \n                $editorName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"hyperGraphPanel\" (localizedPanelLabel(\"Hypergraph Hierarchy\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Hypergraph Hierarchy\")) -mbv $menusOkayInPanels  $panelName;\n\n\t\t\t$editorName = ($panelName+\"HyperGraphEd\");\n            hyperGraph -e \n                -graphLayoutStyle \"hierarchicalLayout\" \n                -orientation \"horiz\" \n                -mergeConnections 0\n                -zoom 1\n                -animateTransition 0\n                -showRelationships 1\n                -showShapes 0\n                -showDeformers 0\n                -showExpressions 0\n                -showConstraints 0\n                -showConnectionFromSelected 0\n                -showConnectionToSelected 0\n"
		+ "                -showConstraintLabels 0\n                -showUnderworld 0\n                -showInvisible 0\n                -transitionFrames 1\n                -opaqueContainers 0\n                -freeform 0\n                -imagePosition 0 0 \n                -imageScale 1\n                -imageEnabled 0\n                -graphType \"DAG\" \n                -heatMapDisplay 0\n                -updateSelection 1\n                -updateNodeAdded 1\n                -useDrawOverrideColor 0\n                -limitGraphTraversal -1\n                -range 0 0 \n                -iconSize \"smallIcons\" \n                -showCachedConnections 0\n                $editorName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"hyperShadePanel\" (localizedPanelLabel(\"Hypershade\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Hypershade\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n"
		+ "\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"visorPanel\" (localizedPanelLabel(\"Visor\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Visor\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"nodeEditorPanel\" (localizedPanelLabel(\"Node Editor\")) `;\n\tif ($nodeEditorPanelVisible || $nodeEditorWorkspaceControlOpen) {\n\t\tif (\"\" == $panelName) {\n\t\t\tif ($useSceneConfig) {\n\t\t\t\t$panelName = `scriptedPanel -unParent  -type \"nodeEditorPanel\" -l (localizedPanelLabel(\"Node Editor\")) -mbv $menusOkayInPanels `;\n\n\t\t\t$editorName = ($panelName+\"NodeEditorEd\");\n            nodeEditor -e \n                -allAttributes 0\n                -allNodes 0\n                -autoSizeNodes 1\n                -consistentNameSize 1\n                -createNodeCommand \"nodeEdCreateNodeCommand\" \n                -connectNodeOnCreation 0\n"
		+ "                -connectOnDrop 0\n                -copyConnectionsOnPaste 0\n                -connectionStyle \"bezier\" \n                -connectionMinSegment 0.03\n                -connectionOffset 0.03\n                -connectionRoundness 0.8\n                -connectionTension -100\n                -defaultPinnedState 0\n                -additiveGraphingMode 0\n                -connectedGraphingMode 1\n                -settingsChangedCallback \"nodeEdSyncControls\" \n                -traversalDepthLimit -1\n                -keyPressCommand \"nodeEdKeyPressCommand\" \n                -nodeTitleMode \"name\" \n                -gridSnap 0\n                -gridVisibility 1\n                -crosshairOnEdgeDragging 0\n                -popupMenuScript \"nodeEdBuildPanelMenus\" \n                -showNamespace 1\n                -showShapes 1\n                -showSGShapes 0\n                -showTransforms 1\n                -useAssets 1\n                -syncedSelection 1\n                -extendToShapes 1\n                -showUnitConversions 0\n"
		+ "                -editorMode \"default\" \n                -hasWatchpoint 0\n                $editorName;\n\t\t\t}\n\t\t} else {\n\t\t\t$label = `panel -q -label $panelName`;\n\t\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Node Editor\")) -mbv $menusOkayInPanels  $panelName;\n\n\t\t\t$editorName = ($panelName+\"NodeEditorEd\");\n            nodeEditor -e \n                -allAttributes 0\n                -allNodes 0\n                -autoSizeNodes 1\n                -consistentNameSize 1\n                -createNodeCommand \"nodeEdCreateNodeCommand\" \n                -connectNodeOnCreation 0\n                -connectOnDrop 0\n                -copyConnectionsOnPaste 0\n                -connectionStyle \"bezier\" \n                -connectionMinSegment 0.03\n                -connectionOffset 0.03\n                -connectionRoundness 0.8\n                -connectionTension -100\n                -defaultPinnedState 0\n                -additiveGraphingMode 0\n                -connectedGraphingMode 1\n                -settingsChangedCallback \"nodeEdSyncControls\" \n"
		+ "                -traversalDepthLimit -1\n                -keyPressCommand \"nodeEdKeyPressCommand\" \n                -nodeTitleMode \"name\" \n                -gridSnap 0\n                -gridVisibility 1\n                -crosshairOnEdgeDragging 0\n                -popupMenuScript \"nodeEdBuildPanelMenus\" \n                -showNamespace 1\n                -showShapes 1\n                -showSGShapes 0\n                -showTransforms 1\n                -useAssets 1\n                -syncedSelection 1\n                -extendToShapes 1\n                -showUnitConversions 0\n                -editorMode \"default\" \n                -hasWatchpoint 0\n                $editorName;\n\t\t\tif (!$useSceneConfig) {\n\t\t\t\tpanel -e -l $label $panelName;\n\t\t\t}\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"createNodePanel\" (localizedPanelLabel(\"Create Node\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Create Node\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n"
		+ "\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"polyTexturePlacementPanel\" (localizedPanelLabel(\"UV Editor\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"UV Editor\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"renderWindowPanel\" (localizedPanelLabel(\"Render View\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Render View\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextPanel \"shapePanel\" (localizedPanelLabel(\"Shape Editor\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tshapePanel -edit -l (localizedPanelLabel(\"Shape Editor\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n"
		+ "\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextPanel \"posePanel\" (localizedPanelLabel(\"Pose Editor\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tposePanel -edit -l (localizedPanelLabel(\"Pose Editor\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"dynRelEdPanel\" (localizedPanelLabel(\"Dynamic Relationships\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Dynamic Relationships\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"relationshipPanel\" (localizedPanelLabel(\"Relationship Editor\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Relationship Editor\")) -mbv $menusOkayInPanels  $panelName;\n"
		+ "\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"referenceEditorPanel\" (localizedPanelLabel(\"Reference Editor\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Reference Editor\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"dynPaintScriptedPanelType\" (localizedPanelLabel(\"Paint Effects\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Paint Effects\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"scriptEditorPanel\" (localizedPanelLabel(\"Script Editor\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Script Editor\")) -mbv $menusOkayInPanels  $panelName;\n"
		+ "\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"profilerPanel\" (localizedPanelLabel(\"Profiler Tool\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Profiler Tool\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\t$panelName = `sceneUIReplacement -getNextScriptedPanel \"contentBrowserPanel\" (localizedPanelLabel(\"Content Browser\")) `;\n\tif (\"\" != $panelName) {\n\t\t$label = `panel -q -label $panelName`;\n\t\tscriptedPanel -edit -l (localizedPanelLabel(\"Content Browser\")) -mbv $menusOkayInPanels  $panelName;\n\t\tif (!$useSceneConfig) {\n\t\t\tpanel -e -l $label $panelName;\n\t\t}\n\t}\n\n\n\tif ($useSceneConfig) {\n        string $configName = `getPanel -cwl (localizedPanelLabel(\"Current Layout\"))`;\n        if (\"\" != $configName) {\n\t\t\tpanelConfiguration -edit -label (localizedPanelLabel(\"Current Layout\")) \n\t\t\t\t-userCreated false\n\t\t\t\t-defaultImage \"\"\n"
		+ "\t\t\t\t-image \"\"\n\t\t\t\t-sc false\n\t\t\t\t-configString \"global string $gMainPane; paneLayout -e -cn \\\"single\\\" -ps 1 100 100 $gMainPane;\"\n\t\t\t\t-removeAllPanels\n\t\t\t\t-ap false\n\t\t\t\t\t(localizedPanelLabel(\"Persp View\")) \n\t\t\t\t\t\"modelPanel\"\n"
		+ "\t\t\t\t\t\"$panelName = `modelPanel -unParent -l (localizedPanelLabel(\\\"Persp View\\\")) -mbv $menusOkayInPanels `;\\n$editorName = $panelName;\\nmodelEditor -e \\n    -cam `findStartUpCamera persp` \\n    -useInteractiveMode 0\\n    -displayLights \\\"default\\\" \\n    -displayAppearance \\\"smoothShaded\\\" \\n    -activeOnly 0\\n    -ignorePanZoom 0\\n    -wireframeOnShaded 0\\n    -headsUpDisplay 1\\n    -holdOuts 1\\n    -selectionHiliteDisplay 1\\n    -useDefaultMaterial 0\\n    -bufferMode \\\"double\\\" \\n    -twoSidedLighting 0\\n    -backfaceCulling 0\\n    -xray 0\\n    -jointXray 0\\n    -activeComponentsXray 0\\n    -displayTextures 0\\n    -smoothWireframe 0\\n    -lineWidth 1\\n    -textureAnisotropic 0\\n    -textureHilight 1\\n    -textureSampling 2\\n    -textureDisplay \\\"modulate\\\" \\n    -textureMaxSize 32768\\n    -fogging 0\\n    -fogSource \\\"fragment\\\" \\n    -fogMode \\\"linear\\\" \\n    -fogStart 0\\n    -fogEnd 100\\n    -fogDensity 0.1\\n    -fogColor 0.5 0.5 0.5 1 \\n    -depthOfFieldPreview 1\\n    -maxConstantTransparency 1\\n    -rendererName \\\"vp2Renderer\\\" \\n    -objectFilterShowInHUD 1\\n    -isFiltered 0\\n    -colorResolution 256 256 \\n    -bumpResolution 512 512 \\n    -textureCompression 0\\n    -transparencyAlgorithm \\\"frontAndBackCull\\\" \\n    -transpInShadows 0\\n    -cullingOverride \\\"none\\\" \\n    -lowQualityLighting 0\\n    -maximumNumHardwareLights 1\\n    -occlusionCulling 0\\n    -shadingModel 0\\n    -useBaseRenderer 0\\n    -useReducedRenderer 0\\n    -smallObjectCulling 0\\n    -smallObjectThreshold -1 \\n    -interactiveDisableShadows 0\\n    -interactiveBackFaceCull 0\\n    -sortTransparent 1\\n    -controllers 1\\n    -nurbsCurves 1\\n    -nurbsSurfaces 1\\n    -polymeshes 1\\n    -subdivSurfaces 1\\n    -planes 1\\n    -lights 1\\n    -cameras 1\\n    -controlVertices 1\\n    -hulls 1\\n    -grid 1\\n    -imagePlane 1\\n    -joints 1\\n    -ikHandles 1\\n    -deformers 1\\n    -dynamics 1\\n    -particleInstancers 1\\n    -fluids 1\\n    -hairSystems 1\\n    -follicles 1\\n    -nCloths 1\\n    -nParticles 1\\n    -nRigids 1\\n    -dynamicConstraints 1\\n    -locators 1\\n    -manipulators 1\\n    -pluginShapes 1\\n    -dimensions 1\\n    -handles 1\\n    -pivots 1\\n    -textures 1\\n    -strokes 1\\n    -motionTrails 1\\n    -clipGhosts 1\\n    -bluePencil 1\\n    -greasePencils 0\\n    -excludeObjectPreset \\\"All\\\" \\n    -shadows 0\\n    -captureSequenceNumber -1\\n    -width 1117\\n    -height 706\\n    -sceneRenderFilter 0\\n    $editorName;\\nmodelEditor -e -viewSelected 0 $editorName;\\nmodelEditor -e \\n    -pluginObjects \\\"gpuCacheDisplayFilter\\\" 1 \\n    $editorName\"\n"
		+ "\t\t\t\t\t\"modelPanel -edit -l (localizedPanelLabel(\\\"Persp View\\\")) -mbv $menusOkayInPanels  $panelName;\\n$editorName = $panelName;\\nmodelEditor -e \\n    -cam `findStartUpCamera persp` \\n    -useInteractiveMode 0\\n    -displayLights \\\"default\\\" \\n    -displayAppearance \\\"smoothShaded\\\" \\n    -activeOnly 0\\n    -ignorePanZoom 0\\n    -wireframeOnShaded 0\\n    -headsUpDisplay 1\\n    -holdOuts 1\\n    -selectionHiliteDisplay 1\\n    -useDefaultMaterial 0\\n    -bufferMode \\\"double\\\" \\n    -twoSidedLighting 0\\n    -backfaceCulling 0\\n    -xray 0\\n    -jointXray 0\\n    -activeComponentsXray 0\\n    -displayTextures 0\\n    -smoothWireframe 0\\n    -lineWidth 1\\n    -textureAnisotropic 0\\n    -textureHilight 1\\n    -textureSampling 2\\n    -textureDisplay \\\"modulate\\\" \\n    -textureMaxSize 32768\\n    -fogging 0\\n    -fogSource \\\"fragment\\\" \\n    -fogMode \\\"linear\\\" \\n    -fogStart 0\\n    -fogEnd 100\\n    -fogDensity 0.1\\n    -fogColor 0.5 0.5 0.5 1 \\n    -depthOfFieldPreview 1\\n    -maxConstantTransparency 1\\n    -rendererName \\\"vp2Renderer\\\" \\n    -objectFilterShowInHUD 1\\n    -isFiltered 0\\n    -colorResolution 256 256 \\n    -bumpResolution 512 512 \\n    -textureCompression 0\\n    -transparencyAlgorithm \\\"frontAndBackCull\\\" \\n    -transpInShadows 0\\n    -cullingOverride \\\"none\\\" \\n    -lowQualityLighting 0\\n    -maximumNumHardwareLights 1\\n    -occlusionCulling 0\\n    -shadingModel 0\\n    -useBaseRenderer 0\\n    -useReducedRenderer 0\\n    -smallObjectCulling 0\\n    -smallObjectThreshold -1 \\n    -interactiveDisableShadows 0\\n    -interactiveBackFaceCull 0\\n    -sortTransparent 1\\n    -controllers 1\\n    -nurbsCurves 1\\n    -nurbsSurfaces 1\\n    -polymeshes 1\\n    -subdivSurfaces 1\\n    -planes 1\\n    -lights 1\\n    -cameras 1\\n    -controlVertices 1\\n    -hulls 1\\n    -grid 1\\n    -imagePlane 1\\n    -joints 1\\n    -ikHandles 1\\n    -deformers 1\\n    -dynamics 1\\n    -particleInstancers 1\\n    -fluids 1\\n    -hairSystems 1\\n    -follicles 1\\n    -nCloths 1\\n    -nParticles 1\\n    -nRigids 1\\n    -dynamicConstraints 1\\n    -locators 1\\n    -manipulators 1\\n    -pluginShapes 1\\n    -dimensions 1\\n    -handles 1\\n    -pivots 1\\n    -textures 1\\n    -strokes 1\\n    -motionTrails 1\\n    -clipGhosts 1\\n    -bluePencil 1\\n    -greasePencils 0\\n    -excludeObjectPreset \\\"All\\\" \\n    -shadows 0\\n    -captureSequenceNumber -1\\n    -width 1117\\n    -height 706\\n    -sceneRenderFilter 0\\n    $editorName;\\nmodelEditor -e -viewSelected 0 $editorName;\\nmodelEditor -e \\n    -pluginObjects \\\"gpuCacheDisplayFilter\\\" 1 \\n    $editorName\"\n"
		+ "\t\t\t\t$configName;\n\n            setNamedPanelLayout (localizedPanelLabel(\"Current Layout\"));\n        }\n\n        panelHistory -e -clear mainPanelHistory;\n        sceneUIReplacement -clear;\n\t}\n\n\ngrid -spacing 5 -size 12 -divisions 5 -displayAxes yes -displayGridLines yes -displayDivisionLines yes -displayPerspectiveLabels no -displayOrthographicLabels no -displayAxesBold yes -perspectiveLabelPosition axis -orthographicLabelPosition edge;\nviewManip -drawCompass 0 -compassAngle 0 -frontParameters \"\" -homeParameters \"\" -selectionLockParameters \"\";\n}\n");
	setAttr ".st" 3;
createNode script -n "sceneConfigurationScriptNode";
	rename -uid "5C95063C-4D56-23F5-6A8B-7BAEB85D99D1";
	setAttr ".b" -type "string" "playbackOptions -min 1 -max 120 -ast 1 -aet 200 ";
	setAttr ".st" 6;
createNode blendColors -n "blendColors1";
	rename -uid "A32D10B8-4607-2CC2-FBF4-33A5664D76BD";
createNode unitConversion -n "unitConversion1";
	rename -uid "130196C3-43F7-0DB4-8E1E-FA8A337A669D";
	setAttr ".cf" 57.295779513082323;
createNode unitConversion -n "unitConversion2";
	rename -uid "AC2DD56D-4696-D34C-2C5F-2D8540C1023B";
	setAttr ".cf" 57.295779513082323;
createNode unitConversion -n "unitConversion3";
	rename -uid "0B73CC98-4CBE-12F2-3EB2-478799BCCF3C";
	setAttr ".cf" 0.017453292519943295;
createNode blendColors -n "blendColors2";
	rename -uid "E2FBA9D1-4D69-9536-8070-56BD4D76FE2A";
createNode blendColors -n "blendColors3";
	rename -uid "AF51B64C-4C03-0B21-0E19-CF9EFC88A171";
createNode unitConversion -n "unitConversion4";
	rename -uid "502A4266-4A24-33CA-D677-4BB172CBED48";
	setAttr ".cf" 57.295779513082323;
createNode unitConversion -n "unitConversion5";
	rename -uid "093C179C-49DA-3074-5310-00B1D08EA1DA";
	setAttr ".cf" 57.295779513082323;
createNode unitConversion -n "unitConversion6";
	rename -uid "05BB8DA9-401C-6401-1673-E282E870E4EB";
	setAttr ".cf" 57.295779513082323;
createNode unitConversion -n "unitConversion7";
	rename -uid "CAB8A42D-44B6-668E-F740-08988551A75F";
	setAttr ".cf" 57.295779513082323;
createNode unitConversion -n "unitConversion8";
	rename -uid "2C6D6703-4F20-B9CB-6AE3-1BB7C0C66D5A";
	setAttr ".cf" 0.017453292519943295;
createNode unitConversion -n "unitConversion9";
	rename -uid "C6DD89D8-4AEE-6166-F75F-B0AD67D88E10";
	setAttr ".cf" 0.017453292519943295;
createNode ikSplineSolver -n "ikSplineSolver";
	rename -uid "9AB5B10A-495E-36BA-8671-65A4019D88B1";
createNode skinCluster -n "skinCluster1";
	rename -uid "F50F04D6-40A6-F662-001E-D89572A35F00";
	setAttr -s 4 ".wl";
	setAttr ".wl[0:3].w"
		1 2 1
		3 0 0.0035124388879126055 1 0.94382397494811909 2 0.052663586163968185
		3 0 0.050969207669216858 1 0.94557288253597327 2 0.0034579097948098658
		1 0 1;
	setAttr -s 3 ".pm";
	setAttr ".pm[0]" -type "matrix" 1 0 0 0 0 1 0 0 0 0 1 0 -0.00016410938405897468 0.0038119496311992407 -8 1;
	setAttr ".pm[1]" -type "matrix" 1 0 0 0 0 1 0 0 0 0 1 0 0 -1.9980922937393188 -8 1;
	setAttr ".pm[2]" -type "matrix" 1 0 0 0 0 1 0 0 0 0 1 0 0 -4 -8 1;
	setAttr ".gm" -type "matrix" 1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1;
	setAttr -s 3 ".ma";
	setAttr -s 3 ".dpf[0:2]"  4 4 4;
	setAttr -s 3 ".lw";
	setAttr -s 3 ".lw";
	setAttr ".mmi" yes;
	setAttr ".mi" 5;
	setAttr ".ucm" yes;
	setAttr -s 3 ".ifcl";
	setAttr -s 3 ".ifcl";
createNode dagPose -n "bindPose1";
	rename -uid "531D13E2-47F7-25DA-8C72-DF83E8E9B1B3";
	setAttr -s 3 ".wm";
	setAttr -s 3 ".xm";
	setAttr ".xm[0]" -type "matrix" "xform" 1 1 1 0 0 0 0 0.00016410938405897468
		 -0.0038119496311992407 14 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 1 1 1 1 yes;
	setAttr ".xm[1]" -type "matrix" "xform" 1 1 1 0 0 0 0 0 1.9980922937393188 14 0
		 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0 0 1 1 1 1 yes;
	setAttr ".xm[2]" -type "matrix" "xform" 1 1 1 0 0 0 0 0 4 14 0 0 0 0 0 0 0 0
		 0 0 0 0 0 0 0 0 0 0 1 0 0 0 1 1 1 1 yes;
	setAttr -s 3 ".m";
	setAttr -s 3 ".p";
	setAttr ".bp" yes;
createNode curveInfo -n "curveInfo1";
	rename -uid "79AF5A98-4939-E8BC-658A-82AD2F71658B";
createNode multiplyDivide -n "multiplyDivide1";
	rename -uid "79D73498-4B89-E47C-09B4-5596FF790480";
	setAttr ".op" 2;
	setAttr ".i2" -type "float3" 4.0009999 1 1 ;
createNode transformGeometry -n "transformGeometry1";
	rename -uid "6AE2261B-40EE-9276-F094-A997923AA464";
	setAttr ".txf" -type "matrix" 1 0 0 0 0 1 0 0 0 0 1 0 0 0.5 -5 1;
createNode blendShape -n "blendShape1";
	rename -uid "4EFA1697-46FF-2456-4401-79ABCA05A65D";
	addAttr -ci true -h true -sn "aal" -ln "attributeAliasList" -dt "attributeAlias";
	setAttr ".w[0]"  1;
	setAttr ".mlid" 0;
	setAttr ".mlpr" 0;
	setAttr ".pndr[0]"  0;
	setAttr ".tgvs[0]" yes;
	setAttr ".tpvs[0]" yes;
	setAttr ".tgdt[0].cid" -type "Int32Array" 1 0 ;
	setAttr ".aal" -type "attributeAlias" 2 "BlendshapeResult" "weight[0]" ;
createNode multMatrix -n "multMatrix1";
	rename -uid "63D76241-41B5-416B-162E-BA8E6159A102";
createNode choice -n "choice1";
	rename -uid "DBE25723-4889-9F5C-1274-51A4E012806C";
	setAttr -s 2 ".i";
createNode multiplyDivide -n "multiplyDivide2";
	rename -uid "71CA8F12-4E45-A360-8730-4FAB886B0C56";
	setAttr ".i2" -type "float3" -50 1 1 ;
createNode unitConversion -n "unitConversion12";
	rename -uid "2E5E3C7E-43B1-E1B1-F262-67A9391E150C";
	setAttr ".cf" 0.017453292519943295;
createNode nodeGraphEditorInfo -n "MayaNodeEditorSavedTabsInfo";
	rename -uid "8C44ADB7-499D-43BF-8AD1-5DA2DDF67F58";
	setAttr -s 5 ".tgi";
	setAttr ".tgi[0].tn" -type "string" "IKFK_Switch";
	setAttr ".tgi[0].vl" -type "double2" -3612.5002821996086 -1952.3809901069094 ;
	setAttr ".tgi[0].vh" -type "double2" 10101.785738624287 1761.9048071995621 ;
	setAttr -s 13 ".tgi[0].ni";
	setAttr ".tgi[0].ni[0].x" 1932.4383544921875;
	setAttr ".tgi[0].ni[0].y" 297.00778198242188;
	setAttr ".tgi[0].ni[0].nvs" 18314;
	setAttr ".tgi[0].ni[1].x" 2239.581298828125;
	setAttr ".tgi[0].ni[1].y" -28.706510543823242;
	setAttr ".tgi[0].ni[1].nvs" 18314;
	setAttr ".tgi[0].ni[2].x" 2208.27197265625;
	setAttr ".tgi[0].ni[2].y" -960.3470458984375;
	setAttr ".tgi[0].ni[2].nvs" 18314;
	setAttr ".tgi[0].ni[3].x" 2921.7392578125;
	setAttr ".tgi[0].ni[3].y" 22.305454254150391;
	setAttr ".tgi[0].ni[3].nvs" 18314;
	setAttr ".tgi[0].ni[4].x" 1551.1290283203125;
	setAttr ".tgi[0].ni[4].y" -633.20416259765625;
	setAttr ".tgi[0].ni[4].nvs" 18346;
	setAttr ".tgi[0].ni[5].x" 1582.4383544921875;
	setAttr ".tgi[0].ni[5].y" 298.43634033203125;
	setAttr ".tgi[0].ni[5].nvs" 18314;
	setAttr ".tgi[0].ni[6].x" 3228.882080078125;
	setAttr ".tgi[0].ni[6].y" -539.12310791015625;
	setAttr ".tgi[0].ni[6].nvs" 18314;
	setAttr ".tgi[0].ni[7].x" 2614.596435546875;
	setAttr ".tgi[0].ni[7].y" 405.16259765625;
	setAttr ".tgi[0].ni[7].nvs" 18314;
	setAttr ".tgi[0].ni[8].x" 3326.620361328125;
	setAttr ".tgi[0].ni[8].y" 95.757843017578125;
	setAttr ".tgi[0].ni[8].nvs" 18314;
	setAttr ".tgi[0].ni[9].x" 3019.477294921875;
	setAttr ".tgi[0].ni[9].y" 657.1864013671875;
	setAttr ".tgi[0].ni[9].nvs" 18314;
	setAttr ".tgi[0].ni[10].x" 1901.1290283203125;
	setAttr ".tgi[0].ni[10].y" -634.63275146484375;
	setAttr ".tgi[0].ni[10].nvs" 18314;
	setAttr ".tgi[0].ni[11].x" 3633.76318359375;
	setAttr ".tgi[0].ni[11].y" -238.52787780761719;
	setAttr ".tgi[0].ni[11].nvs" 18314;
	setAttr ".tgi[0].ni[12].x" 2262.058349609375;
	setAttr ".tgi[0].ni[12].y" 1083.5758056640625;
	setAttr ".tgi[0].ni[12].nvs" 18314;
	setAttr ".tgi[1].tn" -type "string" "Blendshape_Ctrl";
	setAttr ".tgi[1].vl" -type "double2" -512.70258375354513 -775.6163746375222 ;
	setAttr ".tgi[1].vh" -type "double2" 1272.839010508327 79.603600321765711 ;
	setAttr -s 5 ".tgi[1].ni";
	setAttr ".tgi[1].ni[0].x" -194.85823059082031;
	setAttr ".tgi[1].ni[0].y" -144.56289672851562;
	setAttr ".tgi[1].ni[0].nvs" 18314;
	setAttr ".tgi[1].ni[1].x" -201.42857360839844;
	setAttr ".tgi[1].ni[1].y" 52.857143402099609;
	setAttr ".tgi[1].ni[1].nvs" 18312;
	setAttr ".tgi[1].ni[2].x" 664.80352783203125;
	setAttr ".tgi[1].ni[2].y" 37.82659912109375;
	setAttr ".tgi[1].ni[2].nvs" 18314;
	setAttr ".tgi[1].ni[3].x" -201.42857360839844;
	setAttr ".tgi[1].ni[3].y" -48.571430206298828;
	setAttr ".tgi[1].ni[3].nvs" 18312;
	setAttr ".tgi[1].ni[4].x" 340.17864990234375;
	setAttr ".tgi[1].ni[4].y" -21.817842483520508;
	setAttr ".tgi[1].ni[4].nvs" 18314;
	setAttr ".tgi[2].tn" -type "string" "SplineIK";
	setAttr ".tgi[2].vl" -type "double2" -2151.0072405339783 -1222.6189990365315 ;
	setAttr ".tgi[2].vh" -type "double2" 5453.388061690107 836.90472864915819 ;
	setAttr -s 8 ".tgi[2].ni";
	setAttr ".tgi[2].ni[0].x" 3020.69091796875;
	setAttr ".tgi[2].ni[0].y" 334.93011474609375;
	setAttr ".tgi[2].ni[0].nvs" 18313;
	setAttr ".tgi[2].ni[1].x" 1792.1195068359375;
	setAttr ".tgi[2].ni[1].y" 496.35870361328125;
	setAttr ".tgi[2].ni[1].nvs" 18313;
	setAttr ".tgi[2].ni[2].x" 976.1070556640625;
	setAttr ".tgi[2].ni[2].y" -124.50016021728516;
	setAttr ".tgi[2].ni[2].nvs" 18306;
	setAttr ".tgi[2].ni[3].x" 1484.9766845703125;
	setAttr ".tgi[2].ni[3].y" -137.92701721191406;
	setAttr ".tgi[2].ni[3].nvs" 18313;
	setAttr ".tgi[2].ni[4].x" 668.96417236328125;
	setAttr ".tgi[2].ni[4].y" -124.50016021728516;
	setAttr ".tgi[2].ni[4].nvs" 18306;
	setAttr ".tgi[2].ni[5].x" 2406.4052734375;
	setAttr ".tgi[2].ni[5].y" 463.5015869140625;
	setAttr ".tgi[2].ni[5].nvs" 18313;
	setAttr ".tgi[2].ni[6].x" 2713.548095703125;
	setAttr ".tgi[2].ni[6].y" 400.6444091796875;
	setAttr ".tgi[2].ni[6].nvs" 18313;
	setAttr ".tgi[2].ni[7].x" 2099.262451171875;
	setAttr ".tgi[2].ni[7].y" 494.93011474609375;
	setAttr ".tgi[2].ni[7].nvs" 18313;
	setAttr ".tgi[3].tn" -type "string" "OffsetWorld";
	setAttr ".tgi[3].vl" -type "double2" -2089.3014649011684 -426.81145191352687 ;
	setAttr ".tgi[3].vh" -type "double2" 504.3897693018796 826.44271587366029 ;
	setAttr -s 5 ".tgi[3].ni";
	setAttr ".tgi[3].ni[0].x" -88.877449035644531;
	setAttr ".tgi[3].ni[0].y" 99.842597961425781;
	setAttr ".tgi[3].ni[0].nvs" 18314;
	setAttr ".tgi[3].ni[1].x" -339.51336669921875;
	setAttr ".tgi[3].ni[1].y" 43.866855621337891;
	setAttr ".tgi[3].ni[1].nvs" 18314;
	setAttr ".tgi[3].ni[2].x" -1462.507080078125;
	setAttr ".tgi[3].ni[2].y" 389.44757080078125;
	setAttr ".tgi[3].ni[2].nvs" 18306;
	setAttr ".tgi[3].ni[3].x" -892.2279052734375;
	setAttr ".tgi[3].ni[3].y" 165.90359497070312;
	setAttr ".tgi[3].ni[3].nvs" 18314;
	setAttr ".tgi[3].ni[4].x" -635.956298828125;
	setAttr ".tgi[3].ni[4].y" 769.34051513671875;
	setAttr ".tgi[3].ni[4].nvs" 18314;
	setAttr ".tgi[4].tn" -type "string" "SimpleDriverDriven";
	setAttr ".tgi[4].vl" -type "double2" -373.95195666677159 -633.57426361203181 ;
	setAttr ".tgi[4].vh" -type "double2" 1719.0473949211078 377.74895249135523 ;
	setAttr -s 3 ".tgi[4].ni";
	setAttr ".tgi[4].ni[0].x" 771.84869384765625;
	setAttr ".tgi[4].ni[0].y" 37.899158477783203;
	setAttr ".tgi[4].ni[0].nvs" 18306;
	setAttr ".tgi[4].ni[1].x" 472.0238037109375;
	setAttr ".tgi[4].ni[1].y" 71.253501892089844;
	setAttr ".tgi[4].ni[1].nvs" 18306;
	setAttr ".tgi[4].ni[2].x" 155.46218872070312;
	setAttr ".tgi[4].ni[2].y" 73.361343383789062;
	setAttr ".tgi[4].ni[2].nvs" 18306;
select -ne :time1;
	setAttr ".o" 1;
	setAttr ".unw" 1;
select -ne :hardwareRenderingGlobals;
	setAttr ".otfna" -type "stringArray" 22 "NURBS Curves" "NURBS Surfaces" "Polygons" "Subdiv Surface" "Particles" "Particle Instance" "Fluids" "Strokes" "Image Planes" "UI" "Lights" "Cameras" "Locators" "Joints" "IK Handles" "Deformers" "Motion Trails" "Components" "Hair Systems" "Follicles" "Misc. UI" "Ornaments"  ;
	setAttr ".otfva" -type "Int32Array" 22 0 1 1 1 1 1
		 1 1 1 0 0 0 0 0 0 0 0 0
		 0 0 0 0 ;
	setAttr ".msaa" yes;
	setAttr ".fprt" yes;
	setAttr ".rtfm" 1;
select -ne :renderPartition;
	setAttr -s 2 ".st";
select -ne :renderGlobalsList1;
select -ne :defaultShaderList1;
	setAttr -s 6 ".s";
select -ne :postProcessList1;
	setAttr -s 2 ".p";
select -ne :defaultRenderUtilityList1;
	setAttr -s 8 ".u";
select -ne :defaultRenderingList1;
select -ne :standardSurface1;
	setAttr ".bc" -type "float3" 0.40000001 0.40000001 0.40000001 ;
	setAttr ".sr" 0.5;
select -ne :openPBR_shader1;
	setAttr ".bc" -type "float3" 0.40000001 0.40000001 0.40000001 ;
	setAttr ".sr" 0.5;
select -ne :initialShadingGroup;
	setAttr -s 2 ".dsm";
	setAttr ".ro" yes;
select -ne :initialParticleSE;
	setAttr ".ro" yes;
select -ne :defaultRenderGlobals;
	addAttr -ci true -h true -sn "dss" -ln "defaultSurfaceShader" -dt "string";
	setAttr ".ren" -type "string" "arnold";
	setAttr ".dss" -type "string" "openPBR_shader1";
select -ne :defaultResolution;
	setAttr ".pa" 1;
select -ne :defaultColorMgtGlobals;
	setAttr ".cfe" yes;
	setAttr ".cfp" -type "string" "<MAYA_RESOURCES>/OCIO-configs/Maya2022-default/config.ocio";
	setAttr ".vtn" -type "string" "ACES 1.0 SDR-video (sRGB)";
	setAttr ".vn" -type "string" "ACES 1.0 SDR-video";
	setAttr ".dn" -type "string" "sRGB";
	setAttr ".wsn" -type "string" "ACEScg";
	setAttr ".otn" -type "string" "ACES 1.0 SDR-video (sRGB)";
	setAttr ".potn" -type "string" "ACES 1.0 SDR-video (sRGB)";
select -ne :hardwareRenderGlobals;
	setAttr ".ctrs" 256;
	setAttr ".btrs" 512;
select -ne :ikSystem;
	setAttr -s 2 ".sol";
connectAttr "IK_basejoint4.s" "IK_basejoint2.is";
connectAttr "IK_basejoint2.s" "IK_basejoint3.is";
connectAttr "IK_basejoint3.tx" "effector1.tx";
connectAttr "IK_basejoint3.ty" "effector1.ty";
connectAttr "IK_basejoint3.tz" "effector1.tz";
connectAttr "IK_basejoint3.opm" "effector1.opm";
connectAttr "IK_basejoint4.msg" "ikHandle1.hsj";
connectAttr "effector1.hp" "ikHandle1.hee";
connectAttr "ikRPsolver.msg" "ikHandle1.hsv";
connectAttr "FK_basejoint1.s" "FK_basejoint2.is";
connectAttr "FK_basejoint2.s" "FK_basejoint3.is";
connectAttr "unitConversion3.o" "basebindjoint1.r";
connectAttr "basebindjoint1.s" "basebindjoint2.is";
connectAttr "unitConversion8.o" "basebindjoint2.r";
connectAttr "basebindjoint2.s" "basebindjoint3.is";
connectAttr "unitConversion9.o" "basebindjoint3.r";
connectAttr "blendShape1.og[0]" "BlendshapeBaseShape.i";
connectAttr "multiplyDivide1.ox" "basebindsplinejoint.sy";
connectAttr "basebindsplinejoint.s" "basebindsplinejoint1.is";
connectAttr "multiplyDivide1.ox" "basebindsplinejoint1.sy";
connectAttr "basebindsplinejoint1.s" "basebindsplinejoint2.is";
connectAttr "multiplyDivide1.ox" "basebindsplinejoint2.sy";
connectAttr "basebindsplinejoint2.s" "basebindsplinejoint3.is";
connectAttr "multiplyDivide1.ox" "basebindsplinejoint3.sy";
connectAttr "basebindsplinejoint3.s" "basebindsplinejoint4.is";
connectAttr "multiplyDivide1.ox" "basebindsplinejoint4.sy";
connectAttr "basebindsplinejoint4.tx" "effector2.tx";
connectAttr "basebindsplinejoint4.ty" "effector2.ty";
connectAttr "basebindsplinejoint4.tz" "effector2.tz";
connectAttr "basebindsplinejoint4.opm" "effector2.opm";
connectAttr "skinCluster1.og[0]" "splinecurveShape.cr";
connectAttr "basebindsplinejoint.msg" "ikHandle2.hsj";
connectAttr "effector2.hp" "ikHandle2.hee";
connectAttr "ikSplineSolver.msg" "ikHandle2.hsv";
connectAttr "splinecurveShape.ws" "ikHandle2.ic";
connectAttr "multMatrix1.o" "basezerojoint3.opm";
connectAttr "unitConversion12.o" "Drivenbasejoint.rz";
relationship "link" ":lightLinker1" ":initialShadingGroup.message" ":defaultLightSet.message";
relationship "link" ":lightLinker1" ":initialParticleSE.message" ":defaultLightSet.message";
relationship "shadowLink" ":lightLinker1" ":initialShadingGroup.message" ":defaultLightSet.message";
relationship "shadowLink" ":lightLinker1" ":initialParticleSE.message" ":defaultLightSet.message";
connectAttr "blendShape1.mlpr" "shapeEditorManager.bspr[0]";
connectAttr "layerManager.dli[0]" "defaultLayer.id";
connectAttr "renderLayerManager.rlmi[0]" "defaultRenderLayer.rlid";
connectAttr ":defaultArnoldDenoiser.msg" ":defaultArnoldRenderOptions.imagers" -na
		;
connectAttr ":defaultArnoldDisplayDriver.msg" ":defaultArnoldRenderOptions.drivers"
		 -na;
connectAttr ":defaultArnoldFilter.msg" ":defaultArnoldRenderOptions.filt";
connectAttr ":defaultArnoldDriver.msg" ":defaultArnoldRenderOptions.drvr";
connectAttr "IKFK_SwitchCTRL.IKFK_Switch" "blendColors1.b";
connectAttr "unitConversion1.o" "blendColors1.c1";
connectAttr "unitConversion2.o" "blendColors1.c2";
connectAttr "IK_basejoint4.r" "unitConversion1.i";
connectAttr "FK_basejoint1.r" "unitConversion2.i";
connectAttr "blendColors1.op" "unitConversion3.i";
connectAttr "IKFK_SwitchCTRL.IKFK_Switch" "blendColors2.b";
connectAttr "unitConversion7.o" "blendColors2.c1";
connectAttr "unitConversion6.o" "blendColors2.c2";
connectAttr "IKFK_SwitchCTRL.IKFK_Switch" "blendColors3.b";
connectAttr "unitConversion5.o" "blendColors3.c1";
connectAttr "unitConversion4.o" "blendColors3.c2";
connectAttr "FK_basejoint2.r" "unitConversion4.i";
connectAttr "IK_basejoint2.r" "unitConversion5.i";
connectAttr "FK_basejoint3.r" "unitConversion6.i";
connectAttr "IK_basejoint3.r" "unitConversion7.i";
connectAttr "blendColors3.op" "unitConversion8.i";
connectAttr "blendColors2.op" "unitConversion9.i";
connectAttr "splinecurveShape1Orig.ws" "skinCluster1.ip[0].ig";
connectAttr "splinecurveShape1Orig.l" "skinCluster1.orggeom[0]";
connectAttr "bindPose1.msg" "skinCluster1.bp";
connectAttr "Splinectrls1.wm" "skinCluster1.ma[0]";
connectAttr "Splinectrls2.wm" "skinCluster1.ma[1]";
connectAttr "Splinectrls.wm" "skinCluster1.ma[2]";
connectAttr "Splinectrls1.liw" "skinCluster1.lw[0]";
connectAttr "Splinectrls2.liw" "skinCluster1.lw[1]";
connectAttr "Splinectrls.liw" "skinCluster1.lw[2]";
connectAttr "Splinectrls1.obcc" "skinCluster1.ifcl[0]";
connectAttr "Splinectrls2.obcc" "skinCluster1.ifcl[1]";
connectAttr "Splinectrls.obcc" "skinCluster1.ifcl[2]";
connectAttr "Splinectrls1.msg" "bindPose1.m[0]";
connectAttr "Splinectrls2.msg" "bindPose1.m[1]";
connectAttr "Splinectrls.msg" "bindPose1.m[2]";
connectAttr "bindPose1.w" "bindPose1.p[0]";
connectAttr "bindPose1.w" "bindPose1.p[1]";
connectAttr "bindPose1.w" "bindPose1.p[2]";
connectAttr "Splinectrls1.bps" "bindPose1.wm[0]";
connectAttr "Splinectrls2.bps" "bindPose1.wm[1]";
connectAttr "Splinectrls.bps" "bindPose1.wm[2]";
connectAttr "splinecurveShape.ws" "curveInfo1.ic";
connectAttr "curveInfo1.al" "multiplyDivide1.i1x";
connectAttr "BlendshapeBaseShape5Orig.w" "transformGeometry1.ig";
connectAttr "transformGeometry1.og" "blendShape1.ip[0].ig";
connectAttr "BlendshapeBaseShape5Orig.o" "blendShape1.orggeom[0]";
connectAttr "shapeEditorManager.obsv[0]" "blendShape1.tgdt[0].dpvs";
connectAttr "BlendshapeResultShape.w" "blendShape1.it[0].itg[0].iti[6000].igt";
connectAttr "BlendshapeCtrl.Blendshape" "blendShape1.en";
connectAttr "choice1.o" "multMatrix1.i[0]";
connectAttr "basezerojoint2.im" "choice1.i[0]";
connectAttr "basezerojoint1.m" "choice1.i[1]";
connectAttr "basezerojoint3.space" "choice1.s";
connectAttr "Driverbasejoint.tx" "multiplyDivide2.i1x";
connectAttr "multiplyDivide2.ox" "unitConversion12.i";
connectAttr "FK_basejoint2.msg" "MayaNodeEditorSavedTabsInfo.tgi[0].ni[0].dn";
connectAttr "FK_basejoint3.msg" "MayaNodeEditorSavedTabsInfo.tgi[0].ni[1].dn";
connectAttr "IK_basejoint3.msg" "MayaNodeEditorSavedTabsInfo.tgi[0].ni[2].dn";
connectAttr "blendColors3.msg" "MayaNodeEditorSavedTabsInfo.tgi[0].ni[3].dn";
connectAttr "IK_basejoint4.msg" "MayaNodeEditorSavedTabsInfo.tgi[0].ni[4].dn";
connectAttr "FK_basejoint1.msg" "MayaNodeEditorSavedTabsInfo.tgi[0].ni[5].dn";
connectAttr "blendColors2.msg" "MayaNodeEditorSavedTabsInfo.tgi[0].ni[6].dn";
connectAttr "blendColors1.msg" "MayaNodeEditorSavedTabsInfo.tgi[0].ni[7].dn";
connectAttr "basebindjoint2.msg" "MayaNodeEditorSavedTabsInfo.tgi[0].ni[8].dn";
connectAttr "basebindjoint1.msg" "MayaNodeEditorSavedTabsInfo.tgi[0].ni[9].dn";
connectAttr "IK_basejoint2.msg" "MayaNodeEditorSavedTabsInfo.tgi[0].ni[10].dn";
connectAttr "basebindjoint3.msg" "MayaNodeEditorSavedTabsInfo.tgi[0].ni[11].dn";
connectAttr "IKFK_SwitchCTRL.msg" "MayaNodeEditorSavedTabsInfo.tgi[0].ni[12].dn"
		;
connectAttr "BlendshapeCtrl.msg" "MayaNodeEditorSavedTabsInfo.tgi[1].ni[0].dn";
connectAttr "BlendshapeBaseShape5Orig.msg" "MayaNodeEditorSavedTabsInfo.tgi[1].ni[1].dn"
		;
connectAttr "BlendshapeBaseShape.msg" "MayaNodeEditorSavedTabsInfo.tgi[1].ni[2].dn"
		;
connectAttr "BlendshapeResultShape.msg" "MayaNodeEditorSavedTabsInfo.tgi[1].ni[3].dn"
		;
connectAttr "blendShape1.msg" "MayaNodeEditorSavedTabsInfo.tgi[1].ni[4].dn";
connectAttr "basebindsplinejoint4.msg" "MayaNodeEditorSavedTabsInfo.tgi[2].ni[0].dn"
		;
connectAttr "basebindsplinejoint.msg" "MayaNodeEditorSavedTabsInfo.tgi[2].ni[1].dn"
		;
connectAttr "curveInfo1.msg" "MayaNodeEditorSavedTabsInfo.tgi[2].ni[2].dn";
connectAttr "multiplyDivide1.msg" "MayaNodeEditorSavedTabsInfo.tgi[2].ni[3].dn";
connectAttr "splinecurveShape.msg" "MayaNodeEditorSavedTabsInfo.tgi[2].ni[4].dn"
		;
connectAttr "basebindsplinejoint2.msg" "MayaNodeEditorSavedTabsInfo.tgi[2].ni[5].dn"
		;
connectAttr "basebindsplinejoint3.msg" "MayaNodeEditorSavedTabsInfo.tgi[2].ni[6].dn"
		;
connectAttr "basebindsplinejoint1.msg" "MayaNodeEditorSavedTabsInfo.tgi[2].ni[7].dn"
		;
connectAttr "multMatrix1.msg" "MayaNodeEditorSavedTabsInfo.tgi[3].ni[0].dn";
connectAttr "choice1.msg" "MayaNodeEditorSavedTabsInfo.tgi[3].ni[1].dn";
connectAttr "basezerojoint1.msg" "MayaNodeEditorSavedTabsInfo.tgi[3].ni[2].dn";
connectAttr "basezerojoint2.msg" "MayaNodeEditorSavedTabsInfo.tgi[3].ni[3].dn";
connectAttr "basezerojoint3.msg" "MayaNodeEditorSavedTabsInfo.tgi[3].ni[4].dn";
connectAttr "Drivenbasejoint.msg" "MayaNodeEditorSavedTabsInfo.tgi[4].ni[0].dn";
connectAttr "multiplyDivide2.msg" "MayaNodeEditorSavedTabsInfo.tgi[4].ni[1].dn";
connectAttr "Driverbasejoint.msg" "MayaNodeEditorSavedTabsInfo.tgi[4].ni[2].dn";
connectAttr "blendColors1.msg" ":defaultRenderUtilityList1.u" -na;
connectAttr "blendColors2.msg" ":defaultRenderUtilityList1.u" -na;
connectAttr "blendColors3.msg" ":defaultRenderUtilityList1.u" -na;
connectAttr "curveInfo1.msg" ":defaultRenderUtilityList1.u" -na;
connectAttr "multiplyDivide1.msg" ":defaultRenderUtilityList1.u" -na;
connectAttr "multMatrix1.msg" ":defaultRenderUtilityList1.u" -na;
connectAttr "choice1.msg" ":defaultRenderUtilityList1.u" -na;
connectAttr "multiplyDivide2.msg" ":defaultRenderUtilityList1.u" -na;
connectAttr "defaultRenderLayer.msg" ":defaultRenderingList1.r" -na;
connectAttr "BlendshapeResultShape.iog" ":initialShadingGroup.dsm" -na;
connectAttr "BlendshapeBaseShape.iog" ":initialShadingGroup.dsm" -na;
connectAttr "ikRPsolver.msg" ":ikSystem.sol" -na;
connectAttr "ikSplineSolver.msg" ":ikSystem.sol" -na;
// End of BaseFeatures.ma
