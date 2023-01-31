#!/bin/bash

git_details(){

    # Get the current commit hash
    current_commit=$1

    # Get the previous commit hash
    previous_commit=$2

    # Get the list of changed files between the two commits
    changed_files=$(git diff --name-only $previous_commit $current_commit)

    # Filter the names of services which are changed
    changed_services=$(echo "$changed_files" | sed 's/src\///g' | sed 's/\/.*//g')

    # Split the list of changed files into an array
    changed_files_array=$(echo $changed_services | awk '{gsub(/[ \t]+/, ","); print}')
    IFS=',' read -ra changed_files_list <<< "$changed_files_array"

    # Unique entries of services 
    changed_service_list=($(echo "${changed_files_list[@]}" | tr ' ' '\n' | sort -u | tr '\n' ' '))

}

run_build(){

if echo "${changed_service_list[@]}" | grep -q "layers"; then
    echo "BUILDING ALL SERVICES"

    # Run only for service and trigger functions
    pattern1="*-service"
    pattern2="*-trigger"
    folders1=$(find . -type d -name "$pattern1")
    folders2=$(find . -type d -name "$pattern2")
    folders="$folders1 $folders2"
    list_folders=$(echo "$folders" | sed 's/src//g' | sed 's/\.//g' | sed 's/\///g')

    for service_name in ${list_folders[@]}; do

        # Build file
        buildfile=./src/${service_name}/${service_name}.yaml
        sam_build $service_name $buildfile

        # Deploy file
        deployfile=./src/${service_name}/${service_name}-config.toml
        sam_build $service_name $deployfile

    done
    exit
elif echo "${changed_service_list[@]}" | egrep -q "service|trigger"; then
    echo "BUILDING ONLY CHANGED SERVICES - ${changed_service_list[@]}"
    for file in "${changed_service_list[@]}"; do
        if echo $file | egrep -q "migration|iac|scripts|bin|aws_scripts"; then
            echo "----------------------------------------------------"
            echo "Build not applicable for service $file"
            echo "----------------------------------------------------"
        else
            function_name=$(echo $file | cut -d '/' -f 2)
            
            # Build file
            buildfile=./src/${function_name}/${function_name}.yaml
            sam_build $function_name $buildfile

            # Deploy file 
            deployfile=./src/${function_name}/${function_name}-config.toml
            sam_deploy $function_name $deployfile

            # Clean up
            cleanup $function_name
        fi
    done
else
    echo ${changed_service_list[@]}
    echo "NO BACKENDSERVICE MODIFIED"    
fi

}

git_details(){

    # Get the current commit hash
    current_commit=$1

    # Get the previous commit hash
    previous_commit=$2

    # Get the list of changed files between the two commits
    changed_files=$(git diff --name-only $previous_commit $current_commit)

    # Filter the names of services which are changed
    changed_services=$(echo "$changed_files" | sed 's/src\///g' | sed 's/\/.*//g')

    # Split the list of changed files into an array
    changed_files_array=$(echo $changed_services | awk '{gsub(/[ \t]+/, ","); print}')
    IFS=',' read -ra changed_files_list <<< "$changed_files_array"

    # Unique entries of services 
    changed_service_list=($(echo "${changed_files_list[@]}" | tr ' ' '\n' | sort -u | tr '\n' ' '))

}

sam_build(){

    function_name=$1
    buildfile=$2
    ls -ltr $buildfile
    echo "-----------------------------------------------------------"
    echo "| Status - Building | $function_name "
    echo "-----------------------------------------------------------"
#    sam build -t $buildfile --parallel
    echo "-----------------------------------------------------------"
    echo "| Status - Build Completed | $function_name "
    echo "-----------------------------------------------------------"
}

sam_deploy(){
    
    # Variable
    function_name=$1
    deployfile=$2
    ls -ltr $deployfile
    echo "--------------------------------------------------------------"
    echo "| Status - Deploying | $function_name "
    echo "--------------------------------------------------------------"
: '    sam deploy \
    --config-file $deployfile \
    --stack-name $function_name \
    --s3-bucket $SAM_CLI_SOURCE_BUCKET \
    --no-confirm-changeset --no-fail-on-empty-changeset '
    echo "--------------------------------------------------------------"
    echo "| Status - Deployment Completed| $function_name "
    echo "--------------------------------------------------------------"
}

cleanup(){
    echo "Cleaning up build artifacts for $1 ..."
    file_path="./.aws-sam"
    if [ -f "$file_path" ]; then
        rm -r "$file_path"
        echo "Clean up completed"
    else
        echo "Nothing to clean up"
    fi
}

# SCRIPT EXECUTION
start=$(date +%s)
git_details

#LOCAL TESTING
changed_service_list=("layers")

run_build
end=$(date +%s)
echo "-----------------------------------------------------------"
echo "Elapsed Time: $(($end-$start)) seconds"
echo "-----------------------------------------------------------"
